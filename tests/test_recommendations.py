from random import Random

from music_bot.database import SessionFactory, session_scope
from music_bot.repositories import (
    TrackInput,
    add_track_to_library,
    get_or_create_user,
    save_track,
    toggle_track_like,
)
from music_bot.services.recommendations import recommend_tracks


def _track_input(number: int, title: str, artist: str) -> TrackInput:
    return TrackInput(
        telegram_file_id=f"file-{number}",
        telegram_file_unique_id=f"unique-{number}",
        content_hash=f"{number:064x}",
        title=title,
        artist=artist,
        album=None,
        duration=180.0,
        file_size=2048,
    )


def test_recommendations_prioritize_liked_artist(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=1, username="listener")
        first_voter = get_or_create_user(session, telegram_id=2, username="first_voter")
        second_voter = get_or_create_user(session, telegram_id=3, username="second_voter")

        liked_track, _ = save_track(
            session, user, _track_input(1, "First Song", "Favourite Artist")
        )
        same_artist, _ = save_track(
            session, user, _track_input(2, "Second Song", "Favourite Artist")
        )
        popular_track, _ = save_track(
            session, user, _track_input(3, "Popular Song", "Another Artist")
        )
        toggle_track_like(session, user, liked_track)
        toggle_track_like(session, first_voter, popular_track)
        toggle_track_like(session, second_voter, popular_track)

        recommendations = recommend_tracks(session, user, randomizer=Random(0))

        assert recommendations[0] == same_artist
        assert recommendations[1] == popular_track


def test_recommendations_use_popularity_for_cold_start(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=1, username="listener")
        first_voter = get_or_create_user(session, telegram_id=2, username="first_voter")
        second_voter = get_or_create_user(session, telegram_id=3, username="second_voter")
        less_popular, _ = save_track(session, user, _track_input(1, "First", "Artist A"))
        popular, _ = save_track(session, user, _track_input(2, "Second", "Artist B"))

        toggle_track_like(session, first_voter, less_popular)
        toggle_track_like(session, first_voter, popular)
        toggle_track_like(session, second_voter, popular)

        recommendations = recommend_tracks(session, user, randomizer=Random(0))

        assert recommendations[0] == popular
        assert recommendations[1] == less_popular


def test_recommendations_exclude_library_and_liked_tracks(
    database: tuple[object, SessionFactory],
) -> None:
    _, session_factory = database

    with session_scope(session_factory) as session:
        user = get_or_create_user(session, telegram_id=1, username="listener")
        liked_track, _ = save_track(session, user, _track_input(1, "Liked", "Artist A"))
        library_track, _ = save_track(session, user, _track_input(2, "Saved", "Artist B"))
        new_track, _ = save_track(session, user, _track_input(3, "New", "Artist C"))

        toggle_track_like(session, user, liked_track)
        add_track_to_library(session, user, library_track)

        recommendations = recommend_tracks(session, user, randomizer=Random(0))

        assert recommendations == [new_track]
