from dataclasses import replace

from sqlalchemy import Engine, func, select

from music_bot.database import SessionFactory, init_database, session_scope
from music_bot.models import LibraryEntry, Track, TrackLike
from music_bot.repositories import (
    TrackInput,
    add_track_to_library,
    get_liked_track_ids,
    get_or_create_user,
    get_user_library,
    save_track,
    search_tracks,
    toggle_track_like,
)


def _track_input(
    file_id: str = "file-id",
    file_unique_id: str = "unique-id",
    content_hash: str = "a" * 64,
) -> TrackInput:
    return TrackInput(
        telegram_file_id=file_id,
        telegram_file_unique_id=file_unique_id,
        content_hash=content_hash,
        title="Test title",
        artist="Test artist",
        album=None,
        duration=180.0,
        file_size=2048,
    )


def test_save_track(database: tuple[object, SessionFactory]) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        track, created = save_track(session, user, _track_input())

        assert created is True
        assert track.id is not None
        assert track.uploader_user_id == user.id


def test_same_content_hash_does_not_create_second_track(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        first_track, first_created = save_track(session, user, _track_input())
        first_track_id = first_track.id

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        duplicate, duplicate_created = save_track(
            session,
            user,
            _track_input(
                file_id="refreshed-file-id",
                file_unique_id="another-telegram-id",
            ),
        )

        assert first_created is True
        assert duplicate_created is False
        assert duplicate.id == first_track_id
        assert duplicate.telegram_file_id == "refreshed-file-id"
        assert duplicate.telegram_file_unique_id == "another-telegram-id"
        assert session.scalar(select(func.count()).select_from(Track)) == 1


def test_different_content_hash_creates_another_track(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        save_track(session, user, _track_input())
        _, created = save_track(
            session,
            user,
            _track_input(
                file_id="another-file-id",
                file_unique_id="another-unique-id",
                content_hash="b" * 64,
            ),
        )

        assert created is True
        assert session.scalar(select(func.count()).select_from(Track)) == 2


def test_same_track_can_be_added_to_two_personal_libraries(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        first_user = get_or_create_user(session, telegram_id=123, username="first")
        second_user = get_or_create_user(session, telegram_id=456, username="second")
        track, _ = save_track(session, first_user, _track_input())

        assert add_track_to_library(session, first_user, track) is True
        assert add_track_to_library(session, first_user, track) is False
        assert add_track_to_library(session, second_user, track) is True
        assert session.scalar(select(func.count()).select_from(Track)) == 1
        assert session.scalar(select(func.count()).select_from(LibraryEntry)) == 2


def test_user_library_contains_only_own_tracks(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        first_user = get_or_create_user(session, telegram_id=123, username="first")
        second_user = get_or_create_user(session, telegram_id=456, username="second")
        first_track, _ = save_track(session, first_user, _track_input())
        second_track, _ = save_track(
            session,
            second_user,
            _track_input(
                file_id="second-file-id",
                file_unique_id="second-unique-id",
                content_hash="b" * 64,
            ),
        )
        add_track_to_library(session, first_user, first_track)
        add_track_to_library(session, second_user, second_track)

        assert [track.id for track in get_user_library(session, first_user)] == [first_track.id]
        assert [track.id for track in get_user_library(session, second_user)] == [second_track.id]


def test_search_tracks_by_title_and_artist(database: tuple[object, SessionFactory]) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        first, _ = save_track(session, user, _track_input())
        second_data = _track_input(
            file_id="second-file-id",
            file_unique_id="second-unique-id",
            content_hash="b" * 64,
        )
        second_data = replace(second_data, title="Wicked Game", artist="Chris Isaak")
        second, _ = save_track(session, user, second_data)

        assert search_tracks(session, "wicked") == [second]
        assert search_tracks(session, "chris") == [second]
        assert search_tracks(session, "test") == [first]


def test_init_database_adds_old_track_to_uploader_library(
    database: tuple[Engine, SessionFactory],
) -> None:
    engine, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        track, _ = save_track(session, user, _track_input())
        user_id = user.id
        track_id = track.id

    init_database(engine)

    with session_scope(session_factory) as session:
        entry = session.get(LibraryEntry, (user_id, track_id))
        assert entry is not None


def test_like_can_be_added_and_removed(database: tuple[object, SessionFactory]) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=123, username="tester")
        track, _ = save_track(session, user, _track_input())

        assert toggle_track_like(session, user, track) is True
        assert get_liked_track_ids(session, user, [track]) == {track.id}
        assert toggle_track_like(session, user, track) is False
        assert get_liked_track_ids(session, user, [track]) == set()


def test_users_have_independent_likes(database: tuple[object, SessionFactory]) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        first_user = get_or_create_user(session, telegram_id=123, username="first")
        second_user = get_or_create_user(session, telegram_id=456, username="second")
        track, _ = save_track(session, first_user, _track_input())

        toggle_track_like(session, first_user, track)

        assert get_liked_track_ids(session, first_user, [track]) == {track.id}
        assert get_liked_track_ids(session, second_user, [track]) == set()
        assert session.scalar(select(func.count()).select_from(TrackLike)) == 1
