from uuid import UUID

from fetch.domain.entities import (
    ApiOperation,
    ApiSchema,
    AuthDiff,
    AuthScheme,
    OperationDiff,
    SchemaDiff,
    VersionDiff,
)
from fetch.domain.errors import IncompatibleSourceError, RevisionNotFoundError
from fetch.domain.protocols import VersionDiffRepository


class VersionDiffService:
    def __init__(self, repo: VersionDiffRepository) -> None:
        self._repo = repo

    async def diff(
        self,
        source_id: UUID,
        version_a: str,
        version_b: str,
    ) -> VersionDiff:
        rev_a = await self._repo.find_revision_by_source_and_label(source_id, version_a)
        if rev_a is None:
            raise RevisionNotFoundError(
                f"Revision '{version_a}' not found for source {source_id}"
            )

        rev_b = await self._repo.find_revision_by_source_and_label(source_id, version_b)
        if rev_b is None:
            raise RevisionNotFoundError(
                f"Revision '{version_b}' not found for source {source_id}"
            )

        if rev_a.source_id != source_id or rev_b.source_id != source_id:
            raise IncompatibleSourceError(
                "Both revisions must belong to the same source"
            )

        ops_a = await self._repo.list_operations_for_revision(rev_a.id)
        ops_b = await self._repo.list_operations_for_revision(rev_b.id)

        schemas_a = await self._repo.list_schemas_for_revision(rev_a.id)
        schemas_b = await self._repo.list_schemas_for_revision(rev_b.id)

        auth_a = await self._repo.list_auth_for_revision(rev_a.id)
        auth_b = await self._repo.list_auth_for_revision(rev_b.id)

        ops_added, ops_removed, ops_changed = self._diff_operations(ops_a, ops_b)
        schemas_added, schemas_removed, schemas_changed = self._diff_schemas(
            schemas_a, schemas_b
        )
        auth_added, auth_removed = self._diff_auth(auth_a, auth_b)

        summary_parts = []
        if ops_added:
            summary_parts.append(f"{len(ops_added)} operations added")
        if ops_removed:
            summary_parts.append(f"{len(ops_removed)} operations removed")
        if ops_changed:
            summary_parts.append(f"{len(ops_changed)} operations changed")
        if schemas_added:
            summary_parts.append(f"{len(schemas_added)} schemas added")
        if schemas_removed:
            summary_parts.append(f"{len(schemas_removed)} schemas removed")
        if schemas_changed:
            summary_parts.append(f"{len(schemas_changed)} schemas changed")
        if auth_added:
            summary_parts.append(f"{len(auth_added)} auth schemes added")
        if auth_removed:
            summary_parts.append(f"{len(auth_removed)} auth schemes removed")
        summary = ", ".join(summary_parts) if summary_parts else "no changes detected"

        return VersionDiff(
            source_id=source_id,
            revision_a_id=rev_a.id,
            revision_b_id=rev_b.id,
            revision_a_version=version_a,
            revision_b_version=version_b,
            operations_added=ops_added,
            operations_removed=ops_removed,
            operations_changed=ops_changed,
            schemas_added=schemas_added,
            schemas_removed=schemas_removed,
            schemas_changed=schemas_changed,
            auth_added=auth_added,
            auth_removed=auth_removed,
            summary=summary,
        )

    def _diff_operations(
        self,
        ops_a: list[ApiOperation],
        ops_b: list[ApiOperation],
    ) -> tuple[list[OperationDiff], list[OperationDiff], list[OperationDiff]]:
        def key(op: ApiOperation) -> str:
            return f"{op.method.value.upper()} {op.path}"

        map_a = {key(op): op for op in ops_a}
        map_b = {key(op): op for op in ops_b}

        added = [
            OperationDiff(
                operation_id=op.id,
                method=op.method.value,
                path=op.path,
                change_type="added",
                changed_fields=[],
            )
            for k, op in map_b.items()
            if k not in map_a
        ]
        removed = [
            OperationDiff(
                operation_id=op.id,
                method=op.method.value,
                path=op.path,
                change_type="removed",
                changed_fields=[],
            )
            for k, op in map_a.items()
            if k not in map_b
        ]
        changed = []
        for k in map_a.keys() & map_b.keys():
            op_a, op_b = map_a[k], map_b[k]
            fields = []
            if op_a.summary != op_b.summary:
                fields.append("summary")
            if op_a.description != op_b.description:
                fields.append("description")
            if op_a.parameters != op_b.parameters:
                fields.append("parameters")
            if op_a.request_body != op_b.request_body:
                fields.append("request_body")
            if op_a.responses != op_b.responses:
                fields.append("responses")
            if fields:
                changed.append(
                    OperationDiff(
                        operation_id=op_b.id,
                        method=op_b.method.value,
                        path=op_b.path,
                        change_type="changed",
                        changed_fields=fields,
                    )
                )
        return added, removed, changed

    def _diff_schemas(
        self,
        schemas_a: list[ApiSchema],
        schemas_b: list[ApiSchema],
    ) -> tuple[list[SchemaDiff], list[SchemaDiff], list[SchemaDiff]]:
        map_a = {s.name: s for s in schemas_a}
        map_b = {s.name: s for s in schemas_b}

        added = [
            SchemaDiff(
                schema_id=s.id, name=s.name, change_type="added", changed_fields=[]
            )
            for name, s in map_b.items()
            if name not in map_a
        ]
        removed = [
            SchemaDiff(
                schema_id=s.id, name=s.name, change_type="removed", changed_fields=[]
            )
            for name, s in map_a.items()
            if name not in map_b
        ]
        changed = []
        for name in map_a.keys() & map_b.keys():
            s_a, s_b = map_a[name], map_b[name]
            fields = []
            if s_a.schema_json != s_b.schema_json:
                fields.append("definition")
            if s_a.description != s_b.description:
                fields.append("description")
            if fields:
                changed.append(
                    SchemaDiff(
                        schema_id=s_b.id,
                        name=s_b.name,
                        change_type="changed",
                        changed_fields=fields,
                    )
                )
        return added, removed, changed

    def _diff_auth(
        self,
        auth_a: list[AuthScheme],
        auth_b: list[AuthScheme],
    ) -> tuple[list[AuthDiff], list[AuthDiff]]:
        names_a = {a.name for a in auth_a}
        names_b = {a.name for a in auth_b}
        added = [AuthDiff(name=name, change_type="added") for name in names_b - names_a]
        removed = [
            AuthDiff(name=name, change_type="removed") for name in names_a - names_b
        ]
        return added, removed
