from backend.cli.seed import SeedCommand


def test_demo_customer_has_answered_and_pending_tickets(frozen_datetime):
    answered: list[int] = []
    pending: list[int] = []
    in_progress_with_reply = False
    for ticket_id in range(10, 301, 10):
        status = ("new", "in_progress", "closed")[ticket_id % 3]
        comments = SeedCommand.demo_comments(
            {
                "id": ticket_id,
                "author_login": "customer",
                "status": status,
                "created_at": frozen_datetime,
                "response_norm_seconds": 3600,
            }
        )
        staff = [c for c in comments if c["is_staff_reply"]]
        if status == "in_progress" and staff:
            in_progress_with_reply = True
        if status == "closed":
            assert staff, "A completed demo conversation must contain a support response"
            assert staff[0]["author_login"] == "support"
            assert comments[-1]["author_login"] == "customer"
            assert comments[-1]["is_staff_reply"] is False
        (answered if staff else pending).append(ticket_id)
        assert all(c["author_login"] == "customer" for c in comments if not c["is_staff_reply"])
        assert [c["created_at"] for c in comments] == sorted(c["created_at"] for c in comments)
    assert answered and pending
    assert in_progress_with_reply
