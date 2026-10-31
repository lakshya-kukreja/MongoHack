"""In-memory Mock PyMongo Database and Collection for testing MongoDB Atlas integration."""

from copy import deepcopy
from datetime import datetime
from typing import Any, Optional, Union
from pymongo.errors import ConnectionFailure, DuplicateKeyError


class MockCursor:
    """Mock PyMongo Find Cursor supporting .sort() and iteration."""

    def __init__(self, docs: list[dict[str, Any]], projection: Optional[dict[str, Any]] = None):
        self._docs = docs
        self._projection = projection or {}

    def sort(
        self,
        key_or_list: Union[str, list[tuple[str, int]]],
        direction: int = 1,
    ) -> "MockCursor":
        if isinstance(key_or_list, str):
            sort_keys = [(key_or_list, direction)]
        else:
            sort_keys = key_or_list

        def sort_fn(doc: dict[str, Any]) -> tuple:
            res = []
            for k, _ in sort_keys:
                val = doc.get(k)
                if val is None:
                    val = ""
                res.append(val)
            return tuple(res)

        self._docs = sorted(self._docs, key=sort_fn)
        return self

    def __iter__(self):
        for doc in self._docs:
            d = deepcopy(doc)
            if self._projection.get("_id") == 0 and "_id" in d:
                del d["_id"]
            yield d

    def __getitem__(self, index: int) -> dict[str, Any]:
        return list(self)[index]


class MockCollection:
    """Mock PyMongo Collection storing documents in memory with index support."""

    def __init__(self, name: str):
        self.name = name
        self.docs: list[dict[str, Any]] = []
        self.indexes: dict[str, dict[str, Any]] = {}

    def create_index(self, keys: list[tuple[str, int]], **kwargs) -> str:
        name = kwargs.get("name") or "_".join(f"{k}_{d}" for k, d in keys)
        self.indexes[name] = {"keys": keys, "unique": kwargs.get("unique", False)}
        return name

    def _matches(self, doc: dict[str, Any], filter_dict: dict[str, Any]) -> bool:
        for k, v in filter_dict.items():
            doc_val = doc.get(k)
            if isinstance(v, dict):
                for op, op_val in v.items():
                    if op == "$in" and doc_val not in op_val:
                        return False
                    elif op == "$gte" and (doc_val is None or doc_val < op_val):
                        return False
                    elif op == "$lte" and (doc_val is None or doc_val > op_val):
                        return False
                    elif op == "$eq" and doc_val != op_val:
                        return False
            elif doc_val != v:
                return False
        return True

    def _check_unique_constraints(self, doc: dict[str, Any], exclude_doc: Optional[dict[str, Any]] = None) -> None:
        for idx_name, idx_info in self.indexes.items():
            if idx_info.get("unique"):
                keys = idx_info["keys"]
                key_tuple = tuple(doc.get(k) for k, _ in keys)
                for existing in self.docs:
                    if existing is exclude_doc:
                        continue
                    existing_tuple = tuple(existing.get(k) for k, _ in keys)
                    if key_tuple == existing_tuple:
                        raise DuplicateKeyError(
                            f"E11000 duplicate key error collection: {self.name} index: {idx_name} dup key: {key_tuple}"
                        )

    def insert_one(self, doc: dict[str, Any]) -> Any:
        new_doc = deepcopy(doc)
        self._check_unique_constraints(new_doc)
        if "_id" not in new_doc:
            new_doc["_id"] = f"mock_{len(self.docs) + 1}"
        self.docs.append(new_doc)

    def replace_one(
        self,
        filter: dict[str, Any],
        replacement: dict[str, Any],
        upsert: bool = False,
    ) -> None:
        new_doc = deepcopy(replacement)
        for i, existing in enumerate(self.docs):
            if self._matches(existing, filter):
                self._check_unique_constraints(new_doc, exclude_doc=existing)
                if "_id" not in new_doc and "_id" in existing:
                    new_doc["_id"] = existing["_id"]
                self.docs[i] = new_doc
                return
        if upsert:
            self._check_unique_constraints(new_doc)
            if "_id" not in new_doc:
                new_doc["_id"] = f"mock_{len(self.docs) + 1}"
            self.docs.append(new_doc)

    def bulk_write(self, operations: list[Any], ordered: bool = True) -> None:
        for op in operations:
            self.replace_one(op._filter, op._doc, upsert=getattr(op, "_upsert", False))

    def find_one(
        self,
        filter: dict[str, Any],
        projection: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        for doc in self.docs:
            if self._matches(doc, filter):
                res = deepcopy(doc)
                if projection and projection.get("_id") == 0 and "_id" in res:
                    del res["_id"]
                return res
        return None

    def find(
        self,
        filter: Optional[dict[str, Any]] = None,
        projection: Optional[dict[str, Any]] = None,
    ) -> MockCursor:
        filter_dict = filter or {}
        matched = [deepcopy(doc) for doc in self.docs if self._matches(doc, filter_dict)]
        return MockCursor(matched, projection)

    def count_documents(self, filter: dict[str, Any], limit: Optional[int] = None) -> int:
        count = sum(1 for doc in self.docs if self._matches(doc, filter))
        if limit is not None:
            return min(count, limit)
        return count

    def aggregate(self, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = deepcopy(self.docs)
        for stage in pipeline:
            if "$group" in stage:
                group_spec = stage["$group"]
                group_id_field = group_spec["_id"].lstrip("$")
                grouped: dict[str, dict[str, Any]] = {}
                for doc in results:
                    gid = doc.get(group_id_field)
                    if gid not in grouped:
                        grouped[gid] = {
                            "_id": gid,
                            "event_count": 0,
                            "start_time": doc.get("timestamp"),
                            "end_time": doc.get("timestamp"),
                            "services_involved": set(),
                            "events": [],
                        }
                    item = grouped[gid]
                    item["event_count"] += 1
                    ts = doc.get("timestamp")
                    if ts and (item["start_time"] is None or ts < item["start_time"]):
                        item["start_time"] = ts
                    if ts and (item["end_time"] is None or ts > item["end_time"]):
                        item["end_time"] = ts
                    service = doc.get("channel_or_service")
                    if service:
                        item["services_involved"].add(service)
                    item["events"].append({
                        "summary": doc.get("summary", ""),
                        "source_id": doc.get("source_id", ""),
                    })
                out = []
                for g in grouped.values():
                    g["services_involved"] = list(g["services_involved"])
                    out.append(g)
                results = out
            elif "$sort" in stage:
                sort_spec = stage["$sort"]
                sort_field, direction = list(sort_spec.items())[0]
                results = sorted(
                    results,
                    key=lambda d: str(d.get(sort_field, "")),
                    reverse=(direction == -1),
                )
        return results

    def delete_many(self, filter: dict[str, Any]) -> None:
        self.docs = [d for d in self.docs if not self._matches(d, filter)]


class MockAdmin:
    """Mock MongoDB Admin database for ping command."""

    def __init__(self, ping_healthy: bool = True):
        self.ping_healthy = ping_healthy

    def command(self, cmd: str, *args, **kwargs) -> dict[str, Any]:
        if cmd == "ping":
            if not self.ping_healthy:
                raise ConnectionFailure("Could not connect to MongoDB Atlas (mock failure)")
            return {"ok": 1}
        return {"ok": 1}


class MockMongoClient:
    """Mock PyMongo MongoClient instance."""

    def __init__(self, db_name: str = "incident_investigator", ping_healthy: bool = True):
        self.admin = MockAdmin(ping_healthy=ping_healthy)
        self.dbs: dict[str, MockDatabase] = {}
        self.default_db_name = db_name

    def __getitem__(self, name: str) -> "MockDatabase":
        if name not in self.dbs:
            self.dbs[name] = MockDatabase(name, client=self)
        return self.dbs[name]

    def close(self) -> None:
        pass


class MockDatabase:
    """Mock PyMongo Database instance."""

    def __init__(self, name: str, client: Optional[MockMongoClient] = None):
        self.name = name
        self.client = client or MockMongoClient()
        self.collections: dict[str, MockCollection] = {}

    def __getitem__(self, name: str) -> MockCollection:
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]

