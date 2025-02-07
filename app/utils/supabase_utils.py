from dataclasses import fields, is_dataclass

from postgrest import APIResponse


def from_resp(resp: APIResponse, cls) -> list:
    rows = resp.data
    if not rows:
        return []
    if len(rows) == 1:
        return [_to_class(rows[0], cls)]
    return [_to_class(row, cls) for row in rows]


def _to_class(obj: dict, cls):
    if not obj or not is_dataclass(cls):
        return None
    if hasattr(cls, "from_json"):
        return cls.from_json(obj)
    for field in fields(cls):
        if is_dataclass(field.type):
            obj[field.name] = _to_class(obj[field.name], field.type)
    obj = {key: value for key, value in obj.items() if key in fields(cls)}
    return cls(**obj)
