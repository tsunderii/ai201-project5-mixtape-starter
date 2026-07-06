"""
tests/test_feed.py — Mixtape

Regression tests for the "Friends Listening Now" feed.

These guard Issue #2 ("Friends Listening Now shows people from yesterday"): a friend
whose most recent listen is older than the RECENT_THRESHOLD must NOT appear in the
"listening now" feed. Against the buggy 24-hour threshold, a friend who listened two
hours ago was still shown as "listening now"; test_stale_friend_is_excluded below
fails against that buggy value and passes against the 30-minute fix.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def two_friends(app):
    """A user with one friend and one shared song, no listening events yet."""
    with app.app_context():
        me = User(username="me", email="me@example.com")
        friend = User(username="friend", email="friend@example.com")
        db.session.add_all([me, friend])
        db.session.flush()
        db.session.execute(friendships.insert().values(user_id=me.id, friend_id=friend.id))
        db.session.execute(friendships.insert().values(user_id=friend.id, friend_id=me.id))
        song = Song(title="Some Song", artist="Some Artist", shared_by=friend.id)
        db.session.add(song)
        db.session.commit()
        yield {"me": me, "friend": friend, "song": song}


def _add_event(user_id, song_id, minutes_ago):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    db.session.add(ListeningEvent(user_id=user_id, song_id=song_id, listened_at=ts))
    db.session.commit()


def test_recent_friend_is_shown(app, two_friends):
    """A friend who listened within the recency window appears in the feed."""
    with app.app_context():
        me, friend, song = two_friends["me"], two_friends["friend"], two_friends["song"]
        _add_event(friend.id, song.id, minutes_ago=5)
        feed = get_friends_listening_now(me.id)
        assert len(feed) == 1
        assert feed[0]["friend"]["username"] == "friend"


def test_stale_friend_is_excluded(app, two_friends):
    """
    A friend whose most recent listen is 2 hours ago must NOT appear in
    "listening now". This is the Issue #2 regression: the buggy 24-hour
    threshold would include this friend; the 30-minute threshold excludes them.
    """
    with app.app_context():
        me, friend, song = two_friends["me"], two_friends["friend"], two_friends["song"]
        _add_event(friend.id, song.id, minutes_ago=120)
        feed = get_friends_listening_now(me.id)
        assert feed == []
