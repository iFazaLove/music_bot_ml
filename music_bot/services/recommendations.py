from random import Random

from sqlalchemy.orm import Session

from music_bot.models import Track, User
from music_bot.repositories import (
    get_all_tracks,
    get_library_track_ids,
    get_liked_tracks,
    get_track_like_counts,
)


def recommend_tracks(
    session: Session,
    user: User,
    limit: int = 5,
    randomizer: Random | None = None,
) -> list[Track]:
    all_tracks = get_all_tracks(session)
    library_track_ids = get_library_track_ids(session, user, all_tracks)
    liked_tracks = get_liked_tracks(session, user)
    liked_track_ids = {track.id for track in liked_tracks}

    candidates = [
        track
        for track in all_tracks
        if track.id not in library_track_ids and track.id not in liked_track_ids
    ]
    if not candidates:
        return []

    preferred_artists = {track.artist.casefold() for track in liked_tracks}
    like_counts = get_track_like_counts(session, candidates)

    randomizer = randomizer or Random()
    randomizer.shuffle(candidates)
    candidates.sort(
        key=lambda track: (
            track.artist.casefold() in preferred_artists,
            like_counts.get(track.id, 0),
        ),
        reverse=True,
    )
    return candidates[:limit]
