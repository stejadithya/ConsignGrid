"""Sign-in and password rules (UAT round 2, journey 1).

- A password needs at least 10 characters and at most 72 bytes (bcrypt's limit); any characters are allowed.
- A new password can't be the current one or either of the two before it.
- 5 wrong passwords in a row lock the account for 15 minutes; an RM or Administrator can unlock it, and a reset
  password unlocks it too. A right password resets the count.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.identity.models import User

GOOD = "correct-horse-battery"     # the factories' password for every user


def login(world, password, email="rep@example.com"):
    return world.client.post("/api/auth/login", json={"email": email, "password": password})


def change(world, user, current, new, expected=200):
    return world.api(user).post("/auth/password", {"current_password": current, "new_password": new}, expected=expected)


# --- Length and characters ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("new", [
    "abc!@#$%^&*()_+-=[]{}|;:',.<>/?`~",      # every symbol on the keyboard
    "pass word with spaces",                   # spaces, including in the middle
    "ÀéîõüçÑß-tyres",                          # accented letters
    "tyres🙂🚗2026",                           # emoji
    "x" * 72,                                  # exactly the 72-byte limit
])
def test_any_characters_up_to_72_bytes_work_end_to_end(world, new):
    change(world, world.rep, GOOD, new)
    assert login(world, new).status_code == 200
    assert login(world, new + "x").status_code == 401


@pytest.mark.parametrize("new, says", [
    ("short1!", "at least 10"),                # 7 characters
    ("123456789", "at least 10"),              # 9 characters
    ("x" * 73, "72 characters or fewer"),      # one byte too long (used to crash with a server error)
    ("é" * 40, "72 characters or fewer"),      # 40 characters but 80 bytes
])
def test_too_short_or_too_long_is_refused_in_plain_words(world, new, says):
    r = change(world, world.rep, GOOD, new, expected=422)
    assert says in r.text
    assert login(world, GOOD).status_code == 200            # nothing changed


def test_the_same_rules_apply_when_staff_set_a_password(world):
    rm = world.api(world.manager)
    for bad in ("x" * 73, "short"):
        rm.patch(f"/users/{world.rep.id}", {"password": bad}, expected=422)
        rm.post("/users", {"email": "new@example.com", "full_name": "New Person", "password": bad,
                           "role": "SALES_REP"}, expected=422)


# --- Recent passwords -----------------------------------------------------------------------------------------------

def test_the_last_three_passwords_cannot_be_reused(world):
    first, second, third, fourth = "first-password-1", "second-password-2", "third-password-3", "fourth-password-4"
    change(world, world.rep, GOOD, first)
    change(world, world.rep, first, second)
    change(world, world.rep, second, third)
    # The current one and the two before it are refused...
    for again in (third, second, first):
        r = change(world, world.rep, third, again, expected=422)
        assert "haven't used recently" in r.text
    # ...but a password from further back is fine again.
    change(world, world.rep, third, fourth)
    change(world, world.rep, fourth, GOOD)
    assert login(world, GOOD).status_code == 200


# --- Locking after wrong passwords ----------------------------------------------------------------------------------

def test_five_wrong_passwords_lock_the_account_and_an_rm_can_unlock(world):
    for _ in range(4):
        r = login(world, "wrong-password")
        assert r.status_code == 401 and "Invalid email or password" in r.text
    r = login(world, "wrong-password")                       # the 5th
    assert r.status_code == 401 and r.json()["code"] == "account_locked" and "15 more minutes" in r.text
    # Even the right password is refused while locked.
    assert login(world, GOOD).json()["code"] == "account_locked"
    events = world.db.execute(select(AuditEvent.action).where(AuditEvent.entity_id == world.rep.id)).scalars().all()
    assert "user.locked" in events
    # Staff see the lock; a Relationship Manager unlocks it.
    users = world.api(world.manager).get("/users").json()
    assert next(u for u in users if u["id"] == world.rep.id)["locked_until"] is not None
    world.api(world.manager).post(f"/users/{world.rep.id}/unlock")
    assert login(world, GOOD).status_code == 200


def test_a_right_password_resets_the_count(world):
    for _ in range(4):
        login(world, "wrong-password")
    assert login(world, GOOD).status_code == 200
    for _ in range(4):
        assert login(world, "wrong-password").json()["code"] != "account_locked"


def test_the_lock_ends_by_itself_and_a_password_reset_also_unlocks(world):
    for _ in range(5):
        login(world, "wrong-password")
    rep = world.db.get(User, world.rep.id)
    rep.locked_until = datetime.now(UTC) - timedelta(seconds=1)       # 15 minutes later
    world.db.commit()
    assert login(world, GOOD).status_code == 200
    for _ in range(5):
        login(world, "wrong-password")
    world.api(world.manager).patch(f"/users/{world.rep.id}", {"password": "temporary-pass-9"})
    assert login(world, "temporary-pass-9").status_code == 200


def test_only_user_managers_unlock_and_unknown_emails_never_lock(world):
    world.api(world.warehouse_op).post(f"/users/{world.rep.id}/unlock", expected=403)
    for _ in range(6):
        r = login(world, "wrong-password", email="nobody@example.com")
        assert r.status_code == 401 and "Invalid email or password" in r.text


def test_email_is_matched_without_case_or_spaces(world):
    assert login(world, GOOD, email="  Rep@Example.COM ").status_code == 200
