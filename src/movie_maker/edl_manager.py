"""
EDLManager — load Edit Decision List templates from disk.

The engine is stateless: templates ship as JSON files under
`<repo>/library/templates/{with_title|no_title}/`. Firestore-backed
load/save was removed in PR k4 (Apêndice C). The manager keeps two
public surfaces:

  - `load_edl(edl_id, with_title, orientation)` → EDL or None
  - `load_edl_from_file(path)` → EDL or None (used internally; also
    handy for ad-hoc validation in tests)

EDLUtils duration arithmetic helpers stay — they're pure math.
"""

from pathlib import Path
from typing import Optional

from logger import logger
from movie_maker.edl_model import EDL, Duration


class EDLManager:
    # Bundled-template root: `<repo>/library/templates/{with_title|no_title}/{edl_id}.json`.
    # `library/` sits next to `src/`, so we go up three from this file
    # (movie_maker → src → repo root) and join.
    _TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent / "library" / "templates"

    @staticmethod
    def load_edl_from_file(edl_file_path: Path) -> Optional[EDL]:
        """Read a single EDL JSON file from disk. Returns None on any failure."""
        try:
            if not edl_file_path.is_file() or edl_file_path.suffix.lower() != ".json":
                raise FileNotFoundError(
                    f"The file {edl_file_path} does not exist or is not a JSON file"
                )
            json_content = edl_file_path.read_text(encoding="utf-8")
            return EDL.model_validate_json(json_data=json_content)
        except Exception as e:
            logger.exception(e)
            return None

    @staticmethod
    def _resolve_template_file(
        edl_id: str, with_title: bool, orientation: str = "landscape"
    ) -> Optional[Path]:
        """
        Map (edl_id, with_title, orientation) → on-disk path. We try the bare
        edl_id first (sonoma.json, big_sur.json, …) and fall back to the
        orientation-suffixed form (city_beat_landscape.json) since some
        EDL families have separate landscape/portrait templates.
        """
        sub = "with_title" if with_title else "no_title"
        base_dir = EDLManager._TEMPLATES_ROOT / sub
        candidates = [
            base_dir / f"{edl_id.lower()}.json",
            base_dir / f"{edl_id.lower()}_{orientation.lower()}.json",
        ]
        for path in candidates:
            if path.is_file():
                return path
        return None

    @staticmethod
    def load_edl(
        edl_id: str, with_title: bool, orientation: str = "landscape"
    ) -> Optional[EDL]:
        """Load an EDL by id from the bundled template files."""
        template_file = EDLManager._resolve_template_file(
            edl_id=edl_id, with_title=with_title, orientation=orientation,
        )
        if template_file is None:
            logger.error(
                f"EDL '{edl_id}' (with_title={with_title}, orientation={orientation}) not found "
                f"under {EDLManager._TEMPLATES_ROOT}"
            )
            return None
        return EDLManager.load_edl_from_file(template_file)


class EDLUtils:
    @staticmethod
    def duration_to_seconds(duration: Duration, fps: int) -> float:
        return round((duration.seconds + duration.frames / fps), 2)

    @staticmethod
    def add_clip_durations(d1: Duration, d2: Duration, fps: int) -> Duration:
        """
        Add two Duration objects taking into account frames per second (fps).

        This function sums the seconds and frames separately. If the sum of frames
        exceeds or equals the fps, the 'excess' frames are converted into seconds.
        """
        total_seconds = d1.seconds + d2.seconds
        total_frames = d1.frames + d2.frames

        if total_frames >= fps:
            extra_seconds = total_frames // fps
            total_frames = total_frames % fps
            total_seconds += extra_seconds

        return Duration(seconds=total_seconds, frames=total_frames)
