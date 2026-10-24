"""A small orchestrator around the existing Triage approval/health engine."""
import copy
import threading
import time
from triage.experience import ExperienceEngine
from triage.health import check_health
from triage.integrations import ToolAdapter
from triage.tool_engine import ToolEngine
from triage.ecosystem import diagnosis as structured_diagnosis
from .config import validate
from .runtime import Runtime
from .alerts import deliver
from .events import EventStore, normalize
from .contracts import project as contract_records


class DockerAdapter(ToolAdapter):
    """Bind reads and mutations to an immutable container ID and observed daemon ID.

    This narrows the upstream name-based restart: replacing a container under the
    same name must not redirect an approved operation to the replacement.
    """
    def __init__(self, config):
        super().__init__("docker", config)
        self.daemon = None
        self.container_id = None
        self.executed_id = None
        self.executed_daemon = None

    def identity(self):
        raw, _ = self.command(["docker", "--context", "$context", "info", "--format", "{{.ID}}"])
        value = raw.strip()
        if not value or len(value) > 200 or any(c.isspace() for c in value):
            raise ValueError("Docker daemon identity is unavailable")
        return value

    def collect(self):
        before = self.identity()
        snapshot = super().collect()
        after = self.identity()
        if before != after:
            raise ValueError("Docker daemon changed during collection; inspect the Docker context")
        self.daemon = before
        ids = snapshot["observations"].get("id", [])
        self.container_id = ids[0] if len(ids) == 1 else None
        snapshot["observations"]["daemon_id"] = [before]
        self.last_snapshot = snapshot
        return snapshot

    def parse(self, raw):
        import json
        observations = super().parse(raw)
        items = json.loads(raw)
        observations["restart_count"] = [item.get("RestartCount") for item in items]
        return observations

    def repair_allowed(self, snapshot):
        import re
        ids = snapshot["observations"].get("id", [])
        return (len(ids) == 1 and isinstance(ids[0], str) and re.fullmatch(r"[a-f0-9]{64}", ids[0]) is not None
                and super().repair_allowed(snapshot))

    def repair_description(self):
        if not self.container_id:
            self.collect()
        if not self.container_id:
            raise ValueError("Collect the exact container identity before planning")
        return {"command": ["docker", "--context", self.config["context"], "container", "restart", "--time", "10", self.container_id]}

    def verify(self, snapshot):
        return (snapshot["observations"].get("id") == [self.executed_id]
                and snapshot["observations"].get("daemon_id") == [self.executed_daemon]
                and super().verify(snapshot))

    def execute_repair(self):
        import re
        if not self.container_id or not re.fullmatch(r"[a-f0-9]{64}", self.container_id) or self.identity() != self.daemon:
            raise ValueError("Docker identity changed; inspect the target before another plan")
        self.executed_id, self.executed_daemon = self.container_id, self.daemon
        self.command(self.repair_description()["command"], repair=True)


class Pilot:
    def __init__(self, config, state_dir, engine=None, probe=check_health, ai_model=None):
        self.config, self.health = validate(config)
        adapter = DockerAdapter({"context": self.config["docker_context"], "resource": self.config["container"]})
        self.engine = engine or ExperienceEngine(ToolEngine(adapter, state_dir), self.health)
        self.runtime = Runtime(state_dir, self.config)
        self.events = EventStore(self.runtime)
        stored = self.runtime.load()
        self.maintenance_until = stored.get("maintenance_until", 0)
        self.ai_model = ai_model
        self.explanation = None
        self.probe = probe
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.monitor = {"enabled": stored.get("enabled", True), "checked_at": None, "healthy": None, "error": None, "busy": False}
        self.failed = stored.get("failed", False)
        self.monitor_error = False
        self.thread = None
        self.report = self.engine.store.latest(self.engine.adapter.target)[1]
        self.plan_id = None
        self.result = None
        # Stored plans remain reviewable after process restart. Never approve/resend.
        with self.engine.connect() as db:
            for plan_id, payload in db.execute("SELECT id,payload FROM plans ORDER BY rowid DESC LIMIT 100"):
                import json
                if json.loads(payload).get("target") == self.engine.adapter.target:
                    self.plan_id = plan_id
                    break
        if self.plan_id:
            _, outcome = self.engine.store.latest(self.engine.adapter.target, 'outcome:' + self.plan_id)
            if outcome:
                self.result = outcome.get('result')

    def _persist(self):
        self.runtime.save(self.monitor["enabled"], self.maintenance_until, self.failed)

    def _notify(self, event):
        url = self.config.get("alert_url")
        # Persist attempt before I/O. Never replay notifications after restart.
        alert = self.runtime.record(event, "attempting" if url else "local_only")
        if url:
            try:
                deliver(url, event)
            except Exception:
                # Delivery is best effort and must never undo/obscure a repair.
                self.runtime.delivered(alert, "failed")
            else:
                self.runtime.delivered(alert, "sent")

    def diagnosis(self):
        obs = (self.report or {}).get("snapshot", {}).get("observations", {})
        def first(key):
            return (obs.get(key) or [None])[0]
        status, code, oom, restarts = (first(k) for k in ("state", "exit_code", "oom", "restart_count"))
        explanation = "Evidence unavailable; investigate Docker access first."
        if status:
            explanation = "Container state recorded; compare it with the current endpoint check."
        if status in ("exited", "dead", "stopped"):
            explanation = "Container stopped. Exit code alone does not establish why it stopped."
        if oom is True:
            explanation = "Docker reports an out-of-memory kill. Compare memory limits and usage before restarting."
        elif status == "restarting":
            explanation = "Container is restarting. Inspect startup logs and recent deployment changes."
        return dict(state=status, exit_code=code, oom_killed=oom, restart_count=restarts, explanation=explanation)

    def export_report(self):
        state = self.state()
        if state.get("busy"):
            raise ValueError("Wait for the current operation before exporting")
        incident_id = (state.get("plan") or {}).get("incident_id") or (state.get("report") or {}).get("incident_id")
        state["incident_timeline"] = [row for row in self.engine.store.timeline(incident_id) if row["target"] == self.engine.adapter.target] if incident_id else []
        return {"schema_version": 1, "generated_at": time.time(),
                "scope": "One configured Docker app; filtered evidence, not a root-cause guarantee.",
                "structured_diagnosis": structured_diagnosis(state["report"]) if state["report"] else None,
                "contract_records": contract_records(state),
                **{k: state[k] for k in ("name", "container", "context", "health_url", "monitor",
                   "maintenance_until", "diagnosis", "report", "plan", "result", "history", "alerts", "incoming_events", "event_audit", "incident_timeline")}}

    def _investigate(self):
        self.report = self.engine.scan(deep=True)
        return self.report

    def tick(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if not self.monitor["enabled"]:
                return False
            self.monitor["busy"] = True
            if self.maintenance_until and self.maintenance_until <= time.time():
                self.maintenance_until = 0
                self.failed = False
            health = self.probe(self.health)
            if type(health.get("healthy")) is not bool:
                raise ValueError("Health probe did not return a verified outcome")
            self.monitor.update(checked_at=time.time(), healthy=health["healthy"], error=None)
            if self.maintenance_until > time.time():
                self.failed = False
            else:
                if not health["healthy"] and not self.failed:
                    self._investigate()
                    self.failed = True
                    self._persist()
                    self._notify("application_failed")
                elif health["healthy"] and self.failed:
                    self.failed = False
                    self._persist()
                    self._notify("endpoint_recovered")
                self.failed = not health["healthy"]
            self._persist()
            self.monitor_error = False
            return True
        except (ValueError, RuntimeError, OSError):
            if not self.monitor_error and self.maintenance_until <= time.time():
                self._notify("monitor_error")
            self.monitor_error = True
            self.monitor.update(healthy=None, error="Monitoring or investigation failed. Check the configuration, Docker connection and permissions.")
            return False
        finally:
            self.monitor["busy"] = False
            self.lock.release()

    def ingest(self, payload):
        events = normalize(payload, self.config["container"])
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("Pilot is busy; retry the same event ID")
        try:
            receipts = self.events.receive(events)
            # Persist before collection. A retry can finish incomplete investigation;
            # successful receipt alone never claims diagnosis or recovery.
            for receipt, event in zip(receipts, events):
                if receipt["incident_id"] is None:
                    related = self.events.related_incident(event)
                    if related:
                        self.events.link([receipt["id"]], related)
                        receipt["incident_id"] = related
            pending = [r for r in receipts if r["incident_id"] is None]
            failures = {e["id"] for e in events if e["status"] in {"firing", "failed", "rollback_failed"}}
            investigate = [r["id"] for r in pending if r["id"] in failures]
            if investigate and self.maintenance_until <= time.time():
                report = self._investigate()
                incident = report["incident_id"]
                self.events.link(investigate, incident)
                for receipt in receipts:
                    if receipt["id"] in investigate:
                        receipt["incident_id"] = incident
            # Incoming messages cannot plan, approve, execute or mark health recovered.
            return {"receipts": receipts, "repair_executed": False}
        finally:
            self.lock.release()

    def metrics(self):
        with self.runtime.connect() as db:
            counts = db.execute('SELECT COUNT(*), COUNT(DISTINCT incident) FROM incoming_events WHERE target=?', (self.runtime.key,)).fetchone()
            deployment_counts = {status: count for status, count in db.execute(
                "SELECT json_extract(payload,'$.status'),COUNT(*) FROM incoming_events WHERE target=? AND json_extract(payload,'$.kind')='DeploymentEvent' GROUP BY json_extract(payload,'$.status')", (self.runtime.key,))}
        deployment_metrics = "# TYPE ops_pilot_deployment_events_total counter\n" + "".join(
            f'ops_pilot_deployment_events_total{{status="{status}"}} {deployment_counts.get(status, 0)}\n'
            for status in ("started", "succeeded", "failed", "rollback_started", "rollback_succeeded", "rollback_failed"))
        health = self.monitor["healthy"]
        return (deployment_metrics + "# TYPE ops_pilot_endpoint_healthy gauge\n"
                + f"ops_pilot_endpoint_healthy {1 if health is True else 0}\n"
                + "# TYPE ops_pilot_endpoint_known gauge\n"
                + f"ops_pilot_endpoint_known {0 if health is None else 1}\n"
                + "# TYPE ops_pilot_events_total counter\n"
                + f"ops_pilot_events_total {counts[0]}\n"
                + "# TYPE ops_pilot_investigated_incidents_total counter\n"
                + f"ops_pilot_investigated_incidents_total {counts[1]}\n")

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def watch():
            while not self.stop_event.is_set():
                self.tick()
                self.stop_event.wait(self.config["interval_seconds"])
        self.thread = threading.Thread(target=watch, name="ops-pilot-monitor", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def state(self):
        if not self.lock.acquire(blocking=False):
            return {"name": self.config["name"], "busy": True}
        try:
            plan = self.engine.show(self.plan_id) if self.plan_id else None
            return copy.deepcopy({"name": self.config["name"], "container": self.config["container"],
                "context": self.config["docker_context"], "health_url": self.config["health_url"],
                "busy": False, "maintenance_until": self.maintenance_until,
                "diagnosis": self.diagnosis(), "alerts": self.runtime.alerts(),
                "incoming_events": self.events.history(), "event_audit": self.events.audit(),
                "alert_delivery_enabled": bool(self.config.get("alert_url")), "monitor": self.monitor, "report": self.report, "plan": plan, "result": self.result,
                "ai_model": self.ai_model, "explanation": self.explanation, "history": self.engine.history()[:30]})
        finally:
            self.lock.release()

    def action(self, name, plan_id=None):
        try:
            result = self._action(name, plan_id)
        except (ValueError, RuntimeError, OSError):
            self.events.record_action(name, plan_id, "refused_or_failed")
            raise
        self.events.record_action(name, plan_id or self.plan_id, "completed")
        return result

    def _action(self, name, plan_id=None):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A check or repair is running. Wait for it to finish.")
        try:
            if name == "maintenance":
                if self.maintenance_until > time.time():
                    self.maintenance_until = 0
                else:
                    if self.plan_id:
                        plan = self.engine.show(self.plan_id)
                        if plan["status"] in ("pending", "approved"):
                            self.engine.cancel(self.plan_id)
                    self.maintenance_until = time.time() + 3600
                self.failed = False
                self._persist()
                return {"maintenance_until": self.maintenance_until}
            if name in ("plan", "approve", "apply") and self.maintenance_until > time.time():
                raise ValueError("End maintenance before planning or running a repair")
            if name == "explain":
                if not self.ai_model or not self.report:
                    raise ValueError("Optional AI needs a separately installed local model and an incident first")
                from triage.ai import explain
                self.explanation = explain(self.report, self.ai_model)
                return self.explanation
            if name == "investigate":
                return self._investigate()
            if name == "monitor":
                self.monitor["enabled"] = not self.monitor["enabled"]
                if self.monitor["enabled"]:
                    self.failed = False
                self._persist()
                return {"enabled": self.monitor["enabled"]}
            if name == "plan":
                plan = self.engine.plan("restart")
                self.plan_id = plan["id"]
                self.result = None
                return plan
            if name not in ("approve", "apply", "cancel") or not plan_id or plan_id != self.plan_id:
                raise ValueError("Select and review the current exact plan")
            # Approval and application are separate explicit operations.
            if name == "approve":
                return self.engine.approve(plan_id)
            if name == "cancel":
                return self.engine.cancel(plan_id)
            self.result = self.engine.apply(plan_id)
            # ExperienceEngine verifies state AND the configured endpoint. Never
            # infer recovery from the container running flag or an AI response.
            self.monitor.update(healthy=self.result["application_health"]["healthy"], checked_at=time.time())
            self.failed = self.monitor["healthy"] is False
            self.report = self.engine.store.latest(self.engine.adapter.target)[1]
            self._persist()
            self._notify("repair_verified" if self.result["status"] == "verified" else "repair_needs_attention")
            return self.result
        finally:
            self.lock.release()
