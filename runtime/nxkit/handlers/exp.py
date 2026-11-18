"""Experience handlers (exp_search; exp_get/save/replay land in T12)."""

from ..result import make_ok


def handle_exp_search(router, args, request_id):
    query = args.get("q") or ""
    try:
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    hits = router.library.search(query, limit)
    router.gate.mark_searched(router.part)
    return make_ok(
        request_id,
        data={
            "items": [
                {
                    "id": hit["id"],
                    "c": hit.get("c"),
                    "t": hit.get("t"),
                    "v": hit.get("v"),
                }
                for hit in hits
            ]
        },
    )


HANDLERS = {
    "exp_search": handle_exp_search,
}
