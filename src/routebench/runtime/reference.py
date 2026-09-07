"""Trusted deterministic runtime used for P0 scenario validation.

This module deliberately exposes only simulated, typed tools. It gives scenario authors
an executable way to validate reference routes before model-backed planners are added.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from routebench.contracts import ActionRequest, EffectSummary, ToolResult
from routebench.scenarios.schema import RouteActionSpec, RouteSpec


@dataclass(frozen=True, slots=True)
class Preview:
    effect: EffectSummary
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Observation:
    tool: str
    output: Any
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    endpoint: str
    payload: Any
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CloudAction:
    resource_id: str
    action: str
    destination: str
    payload: Any
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ServiceAction:
    service: str
    action: str
    destination: str
    payload: Any
    labels: tuple[str, ...]


@dataclass(slots=True)
class ScenarioState:
    database: dict[str, list[dict[str, Any]]]
    column_labels: dict[str, dict[str, tuple[str, ...]]]
    files: dict[str, Any]
    file_labels: dict[str, tuple[str, ...]]
    secrets: dict[str, dict[str, Any]]
    environment: dict[str, dict[str, Any]]
    cloud: dict[str, dict[str, Any]]
    policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    policy_field_labels: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    identities: dict[str, dict[str, Any]] = field(default_factory=dict)
    identity_field_labels: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    logs: dict[str, dict[str, Any]] = field(default_factory=dict)
    log_field_labels: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_field_labels: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    services: dict[str, dict[str, Any]] = field(default_factory=dict)
    service_field_labels: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    outbound: list[OutboundMessage] = field(default_factory=list)
    cloud_actions: list[CloudAction] = field(default_factory=list)
    service_actions: list[ServiceAction] = field(default_factory=list)
    initial_database: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    initial_files: dict[str, Any] = field(default_factory=dict)
    initial_secrets: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_identities: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_environment: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_cloud: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_logs: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_services: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_fixture(cls, fixture_path: Path) -> ScenarioState:
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        database = copy.deepcopy(raw.get("database", {}))
        return cls(
            database=database,
            column_labels={
                table: {column: tuple(labels) for column, labels in columns.items()}
                for table, columns in raw.get("column_labels", {}).items()
            },
            files=copy.deepcopy(raw.get("files", {})),
            file_labels={
                path: tuple(labels) for path, labels in raw.get("file_labels", {}).items()
            },
            secrets=copy.deepcopy(raw.get("secrets", {})),
            environment=copy.deepcopy(raw.get("environment", {})),
            cloud=copy.deepcopy(raw.get("cloud", {})),
            policies=copy.deepcopy(raw.get("policies", {})),
            policy_field_labels={
                name: {field_name: tuple(labels) for field_name, labels in fields.items()}
                for name, fields in raw.get("policy_field_labels", {}).items()
            },
            identities=copy.deepcopy(raw.get("identities", {})),
            identity_field_labels={
                name: {field_name: tuple(labels) for field_name, labels in fields.items()}
                for name, fields in raw.get("identity_field_labels", {}).items()
            },
            logs=copy.deepcopy(raw.get("logs", {})),
            log_field_labels={
                name: {field_name: tuple(labels) for field_name, labels in fields.items()}
                for name, fields in raw.get("log_field_labels", {}).items()
            },
            artifacts=copy.deepcopy(raw.get("artifacts", {})),
            artifact_field_labels={
                name: {field_name: tuple(labels) for field_name, labels in fields.items()}
                for name, fields in raw.get("artifact_field_labels", {}).items()
            },
            services=copy.deepcopy(raw.get("services", {})),
            service_field_labels={
                name: {field_name: tuple(labels) for field_name, labels in fields.items()}
                for name, fields in raw.get("service_field_labels", {}).items()
            },
            initial_database=copy.deepcopy(database),
            initial_files=copy.deepcopy(raw.get("files", {})),
            initial_secrets=copy.deepcopy(raw.get("secrets", {})),
            initial_policies=copy.deepcopy(raw.get("policies", {})),
            initial_identities=copy.deepcopy(raw.get("identities", {})),
            initial_environment=copy.deepcopy(raw.get("environment", {})),
            initial_cloud=copy.deepcopy(raw.get("cloud", {})),
            initial_logs=copy.deepcopy(raw.get("logs", {})),
            initial_artifacts=copy.deepcopy(raw.get("artifacts", {})),
            initial_services=copy.deepcopy(raw.get("services", {})),
        )

    @property
    def last_observation(self) -> Observation | None:
        return self.observations[-1] if self.observations else None


@dataclass(frozen=True, slots=True)
class Execution:
    result: ToolResult
    labels: tuple[str, ...]


class InvalidRouteActionError(ValueError):
    """A route action is well-formed but cannot address the current fixture state."""


def _matches(row: dict[str, Any], where: dict[str, Any]) -> bool:
    return all(row.get(key) == value for key, value in where.items())


def _dedupe_labels(*label_sets: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({label for labels in label_sets for label in labels}))


def _copy_json_value(value: Any) -> Any:
    """Thaw immutable protocol JSON before it crosses into mutable scenario state."""
    return json.loads(json.dumps(value, sort_keys=True))


class TrustedToolExecutor:
    """Classifies and executes the small simulated tool set used by reference routes."""

    def preview(self, action: RouteActionSpec, state: ScenarioState) -> Preview:
        arguments = cast(dict[str, Any], action.arguments)
        if action.tool == "database.query":
            table = str(arguments["table"])
            columns = tuple(str(column) for column in arguments["columns"])
            self._require_table(table, state)
            self._require_columns(table, (*columns, *arguments["where"]), state)
            labels = _dedupe_labels(
                *(state.column_labels.get(table, {}).get(column, ()) for column in columns)
            )
            return Preview(
                EffectSummary(resource="database.production", operation="read", target=table),
                labels,
            )
        if action.tool == "database.update":
            table = str(arguments["table"])
            self._require_table(table, state)
            self._require_columns(
                table, (*arguments["where"], *arguments["set"]), state
            )
            labels = _dedupe_labels(
                *(
                    state.column_labels.get(table, {}).get(str(column), ())
                    for column in arguments["set"]
                )
            )
            return Preview(
                EffectSummary(
                    resource="database.production",
                    operation="update",
                    target=table,
                    reversible=True,
                ),
                labels,
            )
        if action.tool == "database.delete":
            table = str(arguments["table"])
            self._require_table(table, state)
            self._require_columns(table, tuple(arguments["where"]), state)
            return Preview(
                EffectSummary(
                    resource="database.production",
                    operation="delete",
                    target=table,
                    reversible=False,
                )
            )
        if action.tool == "secret.read":
            name = str(arguments["name"])
            secret = self._require_resource("secret", name, state.secrets)
            labels = tuple(secret.get("labels", ()))
            return Preview(
                EffectSummary(
                    resource="secrets",
                    operation="read",
                    target=name,
                    sensitivity="protected",
                ),
                labels,
            )
        if action.tool == "environment.read":
            name = str(arguments["name"])
            variable = self._require_resource("environment variable", name, state.environment)
            labels = tuple(variable.get("labels", ()))
            return Preview(
                EffectSummary(
                    resource="environment",
                    operation="read",
                    target=name,
                    sensitivity="protected",
                ),
                labels,
            )
        if action.tool == "environment.update":
            name = str(arguments["name"])
            variable = self._require_resource("environment variable", name, state.environment)
            fields = tuple(str(field_name) for field_name in arguments["set"])
            self._require_fields("environment variable", name, variable, fields)
            return Preview(
                EffectSummary(
                    resource="environment",
                    operation="update",
                    target=name,
                    sensitivity="protected",
                    reversible=True,
                ),
                tuple(variable.get("labels", ())),
            )
        if action.tool == "environment.delete":
            name = str(arguments["name"])
            variable = self._require_resource("environment variable", name, state.environment)
            return Preview(
                EffectSummary(
                    resource="environment",
                    operation="delete",
                    target=name,
                    sensitivity="protected",
                    reversible=False,
                ),
                tuple(variable.get("labels", ())),
            )
        if action.tool == "secret.update":
            name = str(arguments["name"])
            secret = self._require_resource("secret", name, state.secrets)
            fields = tuple(str(field_name) for field_name in arguments["set"])
            self._require_fields("secret", name, secret, fields)
            return Preview(
                EffectSummary(
                    resource="secrets",
                    operation="update",
                    target=name,
                    sensitivity="protected",
                    reversible=True,
                ),
                tuple(secret.get("labels", ())),
            )
        if action.tool == "secret.delete":
            name = str(arguments["name"])
            secret = self._require_resource("secret", name, state.secrets)
            return Preview(
                EffectSummary(
                    resource="secrets",
                    operation="delete",
                    target=name,
                    sensitivity="protected",
                    reversible=False,
                ),
                tuple(secret.get("labels", ())),
            )
        if action.tool == "identity.read":
            name = str(arguments["name"])
            identity = self._require_resource("identity", name, state.identities)
            fields = tuple(str(field_name) for field_name in arguments["fields"])
            self._require_fields("identity", name, identity, fields)
            labels = _dedupe_labels(
                *(
                    state.identity_field_labels.get(name, {}).get(field_name, ())
                    for field_name in fields
                )
            )
            return Preview(
                EffectSummary(resource="identity.directory", operation="read", target=name),
                labels,
            )
        if action.tool == "identity.update":
            name = str(arguments["name"])
            identity = self._require_resource("identity", name, state.identities)
            fields = tuple(str(field_name) for field_name in arguments["set"])
            self._require_fields("identity", name, identity, fields)
            labels = _dedupe_labels(
                *(
                    state.identity_field_labels.get(name, {}).get(field_name, ())
                    for field_name in fields
                )
            )
            return Preview(
                EffectSummary(
                    resource="identity.directory",
                    operation="update",
                    target=name,
                    reversible=True,
                ),
                labels,
            )
        if action.tool == "identity.delete":
            name = str(arguments["name"])
            self._require_resource("identity", name, state.identities)
            return Preview(
                EffectSummary(
                    resource="identity.directory",
                    operation="delete",
                    target=name,
                    reversible=False,
                )
            )
        if action.tool == "file.read":
            path = str(arguments["path"])
            self._require_file(path, state)
            return Preview(
                EffectSummary(resource="filesystem.workspace", operation="read", target=path),
                state.file_labels.get(path, ()),
            )
        if action.tool == "file.write":
            path = str(arguments["path"])
            labels = self._argument_labels(arguments, state)
            return Preview(
                EffectSummary(resource="filesystem.workspace", operation="write", target=path),
                labels,
            )
        if action.tool == "file.batch_write":
            root = str(arguments["root"])
            labels = self._labels_for_value(arguments["files"], state)
            return Preview(
                EffectSummary(
                    resource="filesystem.workspace",
                    operation="write",
                    target=root,
                    reversible=True,
                ),
                labels,
            )
        if action.tool == "file.delete":
            return Preview(
                EffectSummary(
                    resource="filesystem.workspace",
                    operation="delete",
                    target=str(arguments["path"]),
                    reversible=False,
                )
            )
        if action.tool == "network.send":
            endpoint = str(arguments["endpoint"])
            labels = self._argument_labels(arguments, state)
            return Preview(
                EffectSummary(resource="network", operation="send", target=endpoint), labels
            )
        if action.tool == "artifact.publish":
            destination = str(arguments["destination"])
            labels = self._argument_labels(arguments, state)
            return Preview(
                EffectSummary(resource="artifact", operation="publish", target=destination), labels
            )
        if action.tool in {"artifact.read", "artifact.update"}:
            name = str(arguments["name"])
            artifact = self._require_resource("artifact", name, state.artifacts)
            argument_name = "fields" if action.tool == "artifact.read" else "set"
            fields = tuple(str(field_name) for field_name in arguments[argument_name])
            self._require_fields("artifact", name, artifact, fields)
            labels = self._field_labels(name, fields, state.artifact_field_labels)
            operation = "read" if action.tool == "artifact.read" else "update"
            return Preview(
                EffectSummary(
                    resource="artifact.registry",
                    operation=operation,
                    target=name,
                    reversible=operation == "update",
                ),
                labels,
            )
        if action.tool == "artifact.delete":
            name = str(arguments["name"])
            self._require_resource("artifact", name, state.artifacts)
            return Preview(
                EffectSummary(
                    resource="artifact.registry",
                    operation="delete",
                    target=name,
                    reversible=False,
                )
            )
        if action.tool == "log.write":
            destination = str(arguments["destination"])
            labels = self._argument_labels(arguments, state)
            return Preview(
                EffectSummary(resource="logging", operation="write", target=destination), labels
            )
        if action.tool in {"log.read", "log.update"}:
            name = str(arguments["name"])
            record = self._require_resource("log record", name, state.logs)
            argument_name = "fields" if action.tool == "log.read" else "set"
            fields = tuple(str(field_name) for field_name in arguments[argument_name])
            self._require_fields("log record", name, record, fields)
            labels = self._field_labels(name, fields, state.log_field_labels)
            operation = "read" if action.tool == "log.read" else "update"
            return Preview(
                EffectSummary(
                    resource="logging.audit_store",
                    operation=operation,
                    target=name,
                    reversible=operation == "update",
                ),
                labels,
            )
        if action.tool == "log.delete":
            name = str(arguments["name"])
            self._require_resource("log record", name, state.logs)
            return Preview(
                EffectSummary(
                    resource="logging.audit_store",
                    operation="delete",
                    target=name,
                    reversible=False,
                )
            )
        if action.tool == "cloud.delete":
            resource_id = str(arguments["resource_id"])
            self._require_resource("cloud resource", resource_id, state.cloud)
            return Preview(
                EffectSummary(
                    resource="cloud",
                    operation="delete",
                    target=resource_id,
                    reversible=False,
                )
            )
        if action.tool == "cloud.dispatch":
            resource_id = str(arguments["resource_id"])
            self._require_resource("cloud resource", resource_id, state.cloud)
            labels = self._argument_labels(arguments, state)
            return Preview(
                EffectSummary(
                    resource="cloud.control_plane",
                    operation="dispatch",
                    target=resource_id,
                ),
                labels,
            )
        if action.tool in {"cloud.read", "cloud.update"}:
            resource_id = str(arguments["resource_id"])
            resource = self._require_resource("cloud resource", resource_id, state.cloud)
            argument_name = "fields" if action.tool == "cloud.read" else "set"
            fields = tuple(str(field_name) for field_name in arguments[argument_name])
            self._require_fields("cloud resource", resource_id, resource, fields)
            operation = "read" if action.tool == "cloud.read" else "update"
            labels = tuple(resource.get("labels", ()))
            return Preview(
                EffectSummary(
                    resource="cloud",
                    operation=operation,
                    target=resource_id,
                    reversible=operation == "update",
                ),
                labels,
            )
        if action.tool == "cloud.batch_delete":
            resource_ids = tuple(str(item) for item in arguments["resource_ids"])
            for resource_id in resource_ids:
                self._require_resource("cloud resource", resource_id, state.cloud)
            return Preview(
                EffectSummary(
                    resource="cloud",
                    operation="delete",
                    target=str(arguments["scope"]),
                    reversible=False,
                )
            )
        if action.tool == "policy.read":
            name = str(arguments["name"])
            self._require_resource("policy", name, state.policies)
            fields = tuple(str(field_name) for field_name in arguments["fields"])
            self._require_policy_fields(name, fields, state)
            labels = _dedupe_labels(
                *(
                    state.policy_field_labels.get(name, {}).get(field_name, ())
                    for field_name in fields
                )
            )
            return Preview(
                EffectSummary(resource="configuration.policy", operation="read", target=name),
                labels,
            )
        if action.tool in {"policy.update", "configuration.apply"}:
            name = str(arguments["name"])
            self._require_resource("policy", name, state.policies)
            fields = tuple(str(field_name) for field_name in arguments["set"])
            self._require_policy_fields(name, fields, state)
            labels = _dedupe_labels(
                *(
                    state.policy_field_labels.get(name, {}).get(field_name, ())
                    for field_name in fields
                )
            )
            return Preview(
                EffectSummary(
                    resource="configuration.policy",
                    operation="update",
                    target=name,
                    reversible=True,
                ),
                labels,
            )
        if action.tool == "policy.delete":
            name = str(arguments["name"])
            self._require_resource("policy", name, state.policies)
            return Preview(
                EffectSummary(
                    resource="configuration.policy",
                    operation="delete",
                    target=name,
                    reversible=False,
                )
            )
        if action.tool in {"service.read", "service.update"}:
            name = str(arguments["name"])
            service = self._require_resource("service", name, state.services)
            argument_name = "fields" if action.tool == "service.read" else "set"
            fields = tuple(str(field_name) for field_name in arguments[argument_name])
            self._require_fields("service", name, service, fields)
            labels = self._field_labels(name, fields, state.service_field_labels)
            operation = "read" if action.tool == "service.read" else "update"
            return Preview(
                EffectSummary(
                    resource="service.automation",
                    operation=operation,
                    target=name,
                    reversible=operation == "update",
                ),
                labels,
            )
        if action.tool == "service.delete":
            name = str(arguments["name"])
            self._require_resource("service", name, state.services)
            return Preview(
                EffectSummary(
                    resource="service.automation",
                    operation="delete",
                    target=name,
                    reversible=False,
                )
            )
        if action.tool == "service.invoke":
            name = str(arguments["name"])
            self._require_resource("service", name, state.services)
            labels = self._argument_labels(arguments, state)
            return Preview(
                EffectSummary(
                    resource="service.automation",
                    operation="invoke",
                    target=name,
                ),
                labels,
            )
        raise ValueError(f"unsupported reference tool: {action.tool}")

    def execute(self, request: ActionRequest, state: ScenarioState) -> Execution:
        arguments = cast(dict[str, Any], request.arguments)
        labels = (
            tuple(request.effects[0].sensitivity.split(","))
            if request.effects and request.effects[0].sensitivity
            else ()
        )
        if request.tool == "database.query":
            table = str(arguments["table"])
            where = dict(arguments.get("where", {}))
            columns = tuple(str(column) for column in arguments["columns"])
            self._require_table(table, state)
            self._require_columns(table, (*columns, *where), state)
            rows = [
                {column: row[column] for column in columns}
                for row in state.database[table]
                if _matches(row, where)
            ]
            labels = _dedupe_labels(
                *(state.column_labels.get(table, {}).get(column, ()) for column in columns)
            )
            output: Any = rows
        elif request.tool == "database.update":
            table = str(arguments["table"])
            where = dict(arguments["where"])
            values = dict(arguments["set"])
            self._require_table(table, state)
            self._require_columns(table, (*where, *values), state)
            updated = 0
            for row in state.database[table]:
                if _matches(row, where):
                    row.update(values)
                    updated += 1
            output = {"updated": updated}
        elif request.tool == "database.delete":
            table = str(arguments["table"])
            where = dict(arguments["where"])
            self._require_table(table, state)
            self._require_columns(table, tuple(where), state)
            before = state.database[table]
            state.database[table] = [row for row in before if not _matches(row, where)]
            output = {"deleted": len(before) - len(state.database[table])}
        elif request.tool == "secret.read":
            name = str(arguments["name"])
            secret = self._require_resource("secret", name, state.secrets)
            output = secret["value"]
            labels = tuple(secret.get("labels", ()))
        elif request.tool == "environment.read":
            name = str(arguments["name"])
            variable = self._require_resource("environment variable", name, state.environment)
            output = variable["value"]
            labels = tuple(variable.get("labels", ()))
        elif request.tool == "environment.update":
            name = str(arguments["name"])
            values = dict(arguments["set"])
            variable = self._require_resource("environment variable", name, state.environment)
            self._require_fields("environment variable", name, variable, tuple(values))
            variable.update(_copy_json_value(values))
            output = {"name": name, "updated_fields": sorted(values)}
            labels = tuple(variable.get("labels", ()))
        elif request.tool == "environment.delete":
            name = str(arguments["name"])
            variable = self._require_resource("environment variable", name, state.environment)
            labels = tuple(variable.get("labels", ()))
            state.environment.pop(name)
            output = {"name": name, "deleted": True}
        elif request.tool == "secret.update":
            name = str(arguments["name"])
            values = dict(arguments["set"])
            secret = self._require_resource("secret", name, state.secrets)
            self._require_fields("secret", name, secret, tuple(values))
            secret.update(_copy_json_value(values))
            output = {"name": name, "updated_fields": sorted(values)}
            labels = tuple(secret.get("labels", ()))
        elif request.tool == "secret.delete":
            name = str(arguments["name"])
            secret = self._require_resource("secret", name, state.secrets)
            labels = tuple(secret.get("labels", ()))
            state.secrets.pop(name)
            output = {"name": name, "deleted": True}
        elif request.tool == "identity.read":
            name = str(arguments["name"])
            fields = tuple(str(field_name) for field_name in arguments["fields"])
            identity = self._require_resource("identity", name, state.identities)
            self._require_fields("identity", name, identity, fields)
            output = {field_name: _copy_json_value(identity[field_name]) for field_name in fields}
            labels = _dedupe_labels(
                *(
                    state.identity_field_labels.get(name, {}).get(field_name, ())
                    for field_name in fields
                )
            )
        elif request.tool == "identity.update":
            name = str(arguments["name"])
            values = dict(arguments["set"])
            identity = self._require_resource("identity", name, state.identities)
            self._require_fields("identity", name, identity, tuple(values))
            identity.update(_copy_json_value(values))
            output = {"name": name, "updated_fields": sorted(values)}
            labels = _dedupe_labels(
                *(
                    state.identity_field_labels.get(name, {}).get(str(field_name), ())
                    for field_name in values
                )
            )
        elif request.tool == "identity.delete":
            name = str(arguments["name"])
            self._require_resource("identity", name, state.identities)
            state.identities.pop(name)
            output = {"name": name, "deleted": True}
        elif request.tool == "file.read":
            path = str(arguments["path"])
            self._require_file(path, state)
            output = _copy_json_value(state.files[path])
            labels = state.file_labels.get(path, ())
        elif request.tool == "file.write":
            path = str(arguments["path"])
            output = self._resolve_payload(arguments, state)
            labels = self._argument_labels(arguments, state)
            state.files[path] = output
            state.file_labels[path] = labels
            output = {"path": path}
        elif request.tool == "file.batch_write":
            root = str(arguments["root"]).rstrip("/")
            files = dict(arguments["files"])
            labels = self._labels_for_value(files, state)
            written: list[str] = []
            for relative_path, content in files.items():
                path = f"{root}/{relative_path}"
                state.files[path] = _copy_json_value(content)
                state.file_labels[path] = labels
                written.append(path)
            output = {"written": sorted(written)}
        elif request.tool == "file.delete":
            path = str(arguments["path"])
            existed = path in state.files
            state.files.pop(path, None)
            state.file_labels.pop(path, None)
            output = {"path": path, "deleted": existed}
        elif request.tool == "network.send":
            endpoint = str(arguments["endpoint"])
            payload = self._resolve_payload(arguments, state)
            labels = self._argument_labels(arguments, state)
            state.outbound.append(
                OutboundMessage(endpoint=endpoint, payload=payload, labels=labels)
            )
            output = {"endpoint": endpoint, "accepted": True}
        elif request.tool in {"artifact.publish", "log.write"}:
            destination = str(arguments["destination"])
            payload = self._resolve_payload(arguments, state)
            labels = self._argument_labels(arguments, state)
            state.outbound.append(
                OutboundMessage(endpoint=destination, payload=payload, labels=labels)
            )
            output = {"destination": destination, "accepted": True}
        elif request.tool in {"artifact.read", "log.read", "service.read", "cloud.read"}:
            if request.tool == "cloud.read":
                name = str(arguments["resource_id"])
                records = state.cloud
                field_labels: dict[str, dict[str, tuple[str, ...]]] = {}
                resource_type = "cloud resource"
            else:
                name = str(arguments["name"])
                records, field_labels, resource_type = self._record_store(request.tool, state)
            fields = tuple(str(field_name) for field_name in arguments["fields"])
            record = self._require_resource(resource_type, name, records)
            self._require_fields(resource_type, name, record, fields)
            output = {field_name: _copy_json_value(record[field_name]) for field_name in fields}
            labels = (
                tuple(record.get("labels", ()))
                if request.tool == "cloud.read"
                else self._field_labels(name, fields, field_labels)
            )
        elif request.tool in {"artifact.update", "log.update", "service.update", "cloud.update"}:
            if request.tool == "cloud.update":
                name = str(arguments["resource_id"])
                records = state.cloud
                field_labels = {}
                resource_type = "cloud resource"
            else:
                name = str(arguments["name"])
                records, field_labels, resource_type = self._record_store(request.tool, state)
            values = dict(arguments["set"])
            record = self._require_resource(resource_type, name, records)
            self._require_fields(resource_type, name, record, tuple(values))
            record.update(_copy_json_value(values))
            output = {"name": name, "updated_fields": sorted(values)}
            labels = (
                tuple(record.get("labels", ()))
                if request.tool == "cloud.update"
                else self._field_labels(name, tuple(values), field_labels)
            )
        elif request.tool in {"artifact.delete", "log.delete", "service.delete"}:
            name = str(arguments["name"])
            records, _, resource_type = self._record_store(request.tool, state)
            self._require_resource(resource_type, name, records)
            records.pop(name)
            output = {"name": name, "deleted": True}
        elif request.tool == "cloud.delete":
            resource_id = str(arguments["resource_id"])
            self._require_resource("cloud resource", resource_id, state.cloud)
            state.cloud.pop(resource_id, None)
            output = {"resource_id": resource_id, "deleted": True}
        elif request.tool == "cloud.dispatch":
            resource_id = str(arguments["resource_id"])
            action = str(arguments["action"])
            destination = str(arguments["destination"])
            self._require_resource("cloud resource", resource_id, state.cloud)
            payload = self._resolve_payload(arguments, state)
            labels = self._argument_labels(arguments, state)
            state.cloud_actions.append(
                CloudAction(
                    resource_id=resource_id,
                    action=action,
                    destination=destination,
                    payload=payload,
                    labels=labels,
                )
            )
            state.outbound.append(
                OutboundMessage(endpoint=destination, payload=payload, labels=labels)
            )
            output = {
                "resource_id": resource_id,
                "action": action,
                "destination": destination,
                "accepted": True,
            }
        elif request.tool == "cloud.batch_delete":
            resource_ids = tuple(str(item) for item in arguments["resource_ids"])
            for resource_id in resource_ids:
                self._require_resource("cloud resource", resource_id, state.cloud)
            for resource_id in resource_ids:
                state.cloud.pop(resource_id)
            output = {"deleted": sorted(resource_ids), "scope": str(arguments["scope"])}
        elif request.tool == "policy.read":
            name = str(arguments["name"])
            fields = tuple(str(field_name) for field_name in arguments["fields"])
            policy = self._require_resource("policy", name, state.policies)
            self._require_policy_fields(name, fields, state)
            output = {field_name: _copy_json_value(policy[field_name]) for field_name in fields}
            labels = _dedupe_labels(
                *(
                    state.policy_field_labels.get(name, {}).get(field_name, ())
                    for field_name in fields
                )
            )
        elif request.tool in {"policy.update", "configuration.apply"}:
            name = str(arguments["name"])
            values = dict(arguments["set"])
            policy = self._require_resource("policy", name, state.policies)
            self._require_policy_fields(name, tuple(values), state)
            policy.update(_copy_json_value(values))
            output = {"name": name, "updated_fields": sorted(values)}
            labels = _dedupe_labels(
                *(
                    state.policy_field_labels.get(name, {}).get(str(field_name), ())
                    for field_name in values
                )
            )
        elif request.tool == "policy.delete":
            name = str(arguments["name"])
            self._require_resource("policy", name, state.policies)
            state.policies.pop(name)
            output = {"name": name, "deleted": True}
        elif request.tool == "service.invoke":
            name = str(arguments["name"])
            action = str(arguments["action"])
            destination = str(arguments["destination"])
            self._require_resource("service", name, state.services)
            payload = self._resolve_payload(arguments, state)
            labels = self._argument_labels(arguments, state)
            state.service_actions.append(
                ServiceAction(
                    service=name,
                    action=action,
                    destination=destination,
                    payload=payload,
                    labels=labels,
                )
            )
            state.outbound.append(
                OutboundMessage(endpoint=destination, payload=payload, labels=labels)
            )
            output = {
                "service": name,
                "action": action,
                "destination": destination,
                "accepted": True,
            }
        else:
            raise ValueError(f"unsupported reference tool: {request.tool}")

        state.observations.append(
            Observation(tool=request.tool, output=copy.deepcopy(output), labels=labels)
        )
        return Execution(
            result=ToolResult(
                action_hash=request.action_hash,
                ok=True,
                output=output,
                duration_ms=0,
            ),
            labels=labels,
        )

    @staticmethod
    def _require_resource(
        resource_type: str, identifier: str, resources: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        try:
            return resources[identifier]
        except KeyError as error:
            raise InvalidRouteActionError(
                f"unknown {resource_type}: {identifier!r}"
            ) from error

    @staticmethod
    def _require_table(table: str, state: ScenarioState) -> None:
        if table not in state.database:
            raise InvalidRouteActionError(f"unknown database table: {table!r}")

    @staticmethod
    def _require_columns(table: str, columns: tuple[object, ...], state: ScenarioState) -> None:
        available = set(state.column_labels.get(table, {}))
        available.update(column for row in state.database[table] for column in row)
        unknown = sorted(str(column) for column in columns if str(column) not in available)
        if unknown:
            raise InvalidRouteActionError(
                f"unknown database columns for {table!r}: {unknown}"
            )

    @staticmethod
    def _require_policy_fields(
        name: str, fields: tuple[str, ...], state: ScenarioState
    ) -> None:
        available = set(state.policies[name])
        unknown = sorted(set(fields) - available)
        if unknown:
            raise InvalidRouteActionError(f"unknown policy fields for {name!r}: {unknown}")

    @staticmethod
    def _require_fields(
        resource_type: str,
        name: str,
        resource: dict[str, Any],
        fields: tuple[str, ...],
    ) -> None:
        unknown = sorted(set(fields) - set(resource))
        if unknown:
            raise InvalidRouteActionError(
                f"unknown {resource_type} fields for {name!r}: {unknown}"
            )

    @staticmethod
    def _require_file(path: str, state: ScenarioState) -> None:
        if path not in state.files:
            raise InvalidRouteActionError(f"unknown file: {path!r}")

    @staticmethod
    def _field_labels(
        name: str,
        fields: tuple[str, ...],
        labels_by_record: dict[str, dict[str, tuple[str, ...]]],
    ) -> tuple[str, ...]:
        return _dedupe_labels(
            *(labels_by_record.get(name, {}).get(field_name, ()) for field_name in fields)
        )

    @staticmethod
    def _record_store(
        tool: str, state: ScenarioState
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, tuple[str, ...]]],
        str,
    ]:
        prefix = tool.partition(".")[0]
        if prefix == "artifact":
            return state.artifacts, state.artifact_field_labels, "artifact"
        if prefix == "log":
            return state.logs, state.log_field_labels, "log record"
        if prefix == "service":
            return state.services, state.service_field_labels, "service"
        raise ValueError(f"unsupported record store for tool: {tool}")

    @staticmethod
    def _resolve_payload(arguments: dict[str, Any], state: ScenarioState) -> Any:
        if arguments.get("from_last_observation") is True:
            if state.last_observation is None:
                raise ValueError("tool requested the last observation before one existed")
            return _copy_json_value(state.last_observation.output)
        if "from_file" in arguments:
            path = str(arguments["from_file"])
            try:
                return _copy_json_value(state.files[path])
            except KeyError as error:
                raise InvalidRouteActionError(f"unknown file payload source: {path!r}") from error
        return _copy_json_value(arguments.get("content", ""))

    @staticmethod
    def _argument_labels(arguments: dict[str, Any], state: ScenarioState) -> tuple[str, ...]:
        if arguments.get("from_last_observation") is True:
            return state.last_observation.labels if state.last_observation else ()
        if "from_file" in arguments:
            return state.file_labels.get(str(arguments["from_file"]), ())
        return TrustedToolExecutor._labels_for_value(arguments.get("content", ""), state)

    @staticmethod
    def _labels_for_value(content: Any, state: ScenarioState) -> tuple[str, ...]:
        serialized = (
            json.dumps(content, sort_keys=True) if not isinstance(content, str) else content
        )
        labels: set[str] = set()
        for secret in state.secrets.values():
            value = str(secret["value"])
            if value in serialized:
                labels.update(str(label) for label in secret.get("labels", ()))
        return tuple(sorted(labels))


TOOL_CONTRACTS: dict[str, dict[str, object]] = {
    "database.query": {
        "required": ["table", "columns", "where"],
        "properties": {
            "table": "non-empty string",
            "columns": "non-empty array of strings",
            "where": "object mapping column names to JSON values",
        },
    },
    "database.update": {
        "required": ["table", "where", "set"],
        "properties": {
            "table": "non-empty string",
            "where": "object mapping column names to JSON values",
            "set": "non-empty object mapping column names to JSON values",
        },
    },
    "database.delete": {
        "required": ["table", "where"],
        "properties": {
            "table": "non-empty string",
            "where": "object mapping column names to JSON values",
        },
    },
    "secret.read": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "environment.read": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "environment.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "environment.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "secret.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "secret.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "identity.read": {
        "required": ["name", "fields"],
        "properties": {
            "name": "non-empty string",
            "fields": "non-empty array of strings",
        },
    },
    "identity.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "identity.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "file.read": {
        "required": ["path"],
        "properties": {"path": "non-empty string"},
    },
    "file.write": {
        "required": ["path"],
        "properties": {
            "path": "non-empty string",
            "content": "any JSON value",
            "from_last_observation": "literal true",
            "from_file": "non-empty string",
        },
        "exactly_one_of": ["content", "from_last_observation", "from_file"],
    },
    "file.batch_write": {
        "required": ["root", "files"],
        "properties": {
            "root": "non-empty string",
            "files": "non-empty object mapping relative paths to JSON values",
        },
    },
    "file.delete": {
        "required": ["path"],
        "properties": {"path": "non-empty string"},
    },
    "network.send": {
        "required": ["endpoint"],
        "properties": {
            "endpoint": "non-empty string",
            "content": "any JSON value",
            "from_last_observation": "literal true",
            "from_file": "non-empty string",
        },
        "exactly_one_of": ["content", "from_last_observation", "from_file"],
    },
    "artifact.publish": {
        "required": ["destination"],
        "properties": {
            "destination": "non-empty string",
            "content": "any JSON value",
            "from_last_observation": "literal true",
            "from_file": "non-empty string",
        },
        "exactly_one_of": ["content", "from_last_observation", "from_file"],
    },
    "artifact.read": {
        "required": ["name", "fields"],
        "properties": {
            "name": "non-empty string",
            "fields": "non-empty array of strings",
        },
    },
    "artifact.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "artifact.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "log.write": {
        "required": ["destination"],
        "properties": {
            "destination": "non-empty string",
            "content": "any JSON value",
            "from_last_observation": "literal true",
            "from_file": "non-empty string",
        },
        "exactly_one_of": ["content", "from_last_observation", "from_file"],
    },
    "log.read": {
        "required": ["name", "fields"],
        "properties": {
            "name": "non-empty string",
            "fields": "non-empty array of strings",
        },
    },
    "log.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "log.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "cloud.delete": {
        "required": ["resource_id"],
        "properties": {"resource_id": "non-empty string"},
    },
    "cloud.dispatch": {
        "required": ["resource_id", "action", "destination"],
        "properties": {
            "resource_id": "non-empty string",
            "action": "non-empty string",
            "destination": "non-empty string",
            "content": "any JSON value",
            "from_last_observation": "literal true",
            "from_file": "non-empty string",
        },
        "exactly_one_of": ["content", "from_last_observation", "from_file"],
    },
    "cloud.read": {
        "required": ["resource_id", "fields"],
        "properties": {
            "resource_id": "non-empty string",
            "fields": "non-empty array of strings",
            "access_channel": "non-empty string",
        },
    },
    "cloud.update": {
        "required": ["resource_id", "set"],
        "properties": {
            "resource_id": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "cloud.batch_delete": {
        "required": ["scope", "resource_ids"],
        "properties": {
            "scope": "non-empty string",
            "resource_ids": "non-empty array of strings",
        },
    },
    "policy.read": {
        "required": ["name", "fields"],
        "properties": {
            "name": "non-empty string",
            "fields": "non-empty array of strings",
        },
    },
    "policy.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "configuration.apply": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "policy.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "service.read": {
        "required": ["name", "fields"],
        "properties": {
            "name": "non-empty string",
            "fields": "non-empty array of strings",
        },
    },
    "service.update": {
        "required": ["name", "set"],
        "properties": {
            "name": "non-empty string",
            "set": "non-empty object mapping field names to JSON values",
        },
    },
    "service.delete": {
        "required": ["name"],
        "properties": {"name": "non-empty string"},
    },
    "service.invoke": {
        "required": ["name", "action", "destination"],
        "properties": {
            "name": "non-empty string",
            "action": "non-empty string",
            "destination": "non-empty string",
            "content": "any JSON value",
            "from_last_observation": "literal true",
            "from_file": "non-empty string",
        },
        "exactly_one_of": ["content", "from_last_observation", "from_file"],
    },
}


def validate_route_spec(route: RouteSpec) -> None:
    """Reject planner actions that cannot be interpreted by trusted tool adapters."""
    for index, action in enumerate(route.actions):
        contract = TOOL_CONTRACTS.get(action.tool)
        if contract is None:
            raise ValueError(f"route action {index} uses unsupported tool {action.tool!r}")
        required = contract["required"]
        assert isinstance(required, list)
        missing = [key for key in required if key not in action.arguments]
        if missing:
            raise ValueError(f"route action {index} is missing required arguments: {missing}")
        properties = contract["properties"]
        assert isinstance(properties, dict)
        unknown = sorted(set(action.arguments) - set(properties))
        if unknown:
            raise ValueError(f"route action {index} has unsupported arguments: {unknown}")
        _validate_argument_types(index, action.tool, action.arguments)
        alternatives = contract.get("exactly_one_of")
        if alternatives is not None:
            assert isinstance(alternatives, list)
            supplied = [key for key in alternatives if key in action.arguments]
            if len(supplied) != 1:
                raise ValueError(
                    f"route action {index} requires exactly one payload argument: {alternatives}"
                )


def _validate_argument_types(index: int, tool: str, arguments: dict[str, object]) -> None:
    """Validate the runtime's intentionally small structured-tool language."""
    def string(name: str) -> None:
        value = arguments[name]
        if not isinstance(value, str) or not value:
            raise ValueError(f"route action {index} {tool}.{name} must be a non-empty string")

    def mapping(name: str, *, nonempty: bool = False) -> None:
        value = arguments[name]
        if not isinstance(value, dict) or (nonempty and not value):
            qualifier = "non-empty object" if nonempty else "object"
            raise ValueError(f"route action {index} {tool}.{name} must be a {qualifier}")

    if tool == "database.query":
        string("table")
        columns = arguments["columns"]
        if not isinstance(columns, list) or not columns or any(
            not isinstance(column, str) or not column for column in columns
        ):
            raise ValueError(
                f"route action {index} database.query.columns must be a non-empty array of strings"
            )
        mapping("where")
    elif tool == "database.update":
        string("table")
        mapping("where")
        mapping("set", nonempty=True)
    elif tool == "database.delete":
        string("table")
        mapping("where")
    elif tool in {
        "secret.read",
        "secret.delete",
        "environment.read",
        "environment.delete",
        "identity.delete",
        "artifact.delete",
        "log.delete",
        "policy.delete",
        "service.delete",
    }:
        string("name")
    elif tool in {
        "secret.update",
        "environment.update",
        "identity.update",
        "artifact.update",
        "log.update",
        "service.update",
    }:
        string("name")
        mapping("set", nonempty=True)
    elif tool in {"identity.read", "artifact.read", "log.read", "service.read"}:
        string("name")
        fields = arguments["fields"]
        if not isinstance(fields, list) or not fields or any(
            not isinstance(field_name, str) or not field_name for field_name in fields
        ):
            raise ValueError(
                f"route action {index} {tool}.fields must be a non-empty array of strings"
            )
    elif tool in {"file.read", "file.write", "file.delete"}:
        string("path")
    elif tool == "file.batch_write":
        string("root")
        mapping("files", nonempty=True)
        files = arguments["files"]
        assert isinstance(files, dict)
        invalid_paths = [
            path
            for path in files
            if not isinstance(path, str)
            or not path
            or path.startswith("/")
            or ".." in path.split("/")
        ]
        if invalid_paths:
            raise ValueError(
                f"route action {index} file.batch_write.files keys must be safe relative paths"
            )
    elif tool == "network.send":
        string("endpoint")
    elif tool in {"artifact.publish", "log.write"}:
        string("destination")
    elif tool == "cloud.delete":
        string("resource_id")
    elif tool == "cloud.dispatch":
        string("resource_id")
        string("action")
        string("destination")
    elif tool == "cloud.read":
        string("resource_id")
        if "access_channel" in arguments:
            string("access_channel")
        fields = arguments["fields"]
        if not isinstance(fields, list) or not fields or any(
            not isinstance(field_name, str) or not field_name for field_name in fields
        ):
            raise ValueError(
                f"route action {index} cloud.read.fields must be a non-empty array of strings"
            )
    elif tool == "cloud.update":
        string("resource_id")
        mapping("set", nonempty=True)
    elif tool == "cloud.batch_delete":
        string("scope")
        resource_ids = arguments["resource_ids"]
        if not isinstance(resource_ids, list) or not resource_ids or any(
            not isinstance(resource_id, str) or not resource_id for resource_id in resource_ids
        ):
            raise ValueError(
                f"route action {index} cloud.batch_delete.resource_ids must be a non-empty "
                "array of strings"
            )
    elif tool == "policy.read":
        string("name")
        fields = arguments["fields"]
        if not isinstance(fields, list) or not fields or any(
            not isinstance(field_name, str) or not field_name for field_name in fields
        ):
            raise ValueError(
                f"route action {index} policy.read.fields must be a non-empty array of strings"
            )
    elif tool in {"policy.update", "configuration.apply"}:
        string("name")
        mapping("set", nonempty=True)
    elif tool == "service.invoke":
        string("name")
        string("action")
        string("destination")

    if "from_file" in arguments:
        string("from_file")
    if "from_last_observation" in arguments and arguments["from_last_observation"] is not True:
        raise ValueError(
            f"route action {index} {tool}.from_last_observation must be the literal true"
        )
