import subprocess
from io import BytesIO

import sys
# Create an alias so that any import of 'pyaudioop' will actually use 'audioop'
sys.modules["pyaudioop"] = 'audioop'

from pydub import AudioSegment

from pathlib import Path
from typing import Iterator, Literal

from logger import logger

def adjust_audio(
        audio_in: Iterator[bytes], 
        format: Literal['mp3', 'wav'],
        allowable_adjustment_factor: tuple[float, float],
        desired_duration_window: tuple[float, float] = None,
    ) -> Iterator[bytes]:
        """
        Adjust the audio (supplied as an iterator of bytes) so that its total duration
        falls within a specified window. The function uses FFmpeg's 'atempo' filter to
        speed up or slow down the audio.

        Parameters:
        audio_in: Iterator yielding chunks of audio bytes.
        format: Output format ('mp3' or 'wav')
        desired_duration_window: Tuple (min_duration, max_duration) in seconds.
            - If provided and the audio's duration is outside this window,
                the target duration is set to max_duration (if too long) or 
                min_duration (if too short). If the audio already falls within
                the window, the original audio is returned.
        allowable_adjustment_factor: Tuple (min_factor, max_factor) that limits
            how much the audio can be sped up (factor > 1) or slowed down (factor < 1).
            For example, (0.9, 1.1) would limit adjustments to ±10%. This clamping is
            applied on top of FFmpeg's atempo allowed range (0.5 to 2.0).

        Returns:
        An iterator yielding chunks (bytes) of the adjusted audio in the specified format.

        Raises:
        RuntimeError: If FFmpeg fails.
        ValueError: If the computed factor is outside FFmpeg's one-pass range.
        """
        # 1. Read all input bytes into memory.
        input_bytes = b"".join(audio_in)
        
        # 2. Convert raw PCM to WAV if needed (ElevenLabs sends raw PCM)
        if format == "wav":
            # Create WAV from raw PCM (s16le, 24kHz, mono)
            pcm = AudioSegment.from_raw(
                BytesIO(input_bytes),
                sample_width=2,  # 16-bit
                frame_rate=24000,
                channels=1
            )
            wav_io = BytesIO()
            pcm.export(wav_io, format="wav")
            wav_io.seek(0)
            input_bytes = wav_io.read()
        
        # 3. Load audio with pydub
        audio = AudioSegment.from_file(BytesIO(input_bytes), format=format)
        original_duration = len(audio) / 1000.0  # duration in seconds

        # 4. If no desired window or already within window, return original
        if desired_duration_window is None:
            yield input_bytes
            return

        min_duration, max_duration = desired_duration_window

        if min_duration <= original_duration <= max_duration:
            yield input_bytes
            return

        # 5. Determine target duration and compute factor
        target_duration = max_duration if original_duration > max_duration else min_duration
        factor = original_duration / target_duration
        
        # 6. Clamp factor within allowable range
        if allowable_adjustment_factor is not None:
            min_factor_allowed, max_factor_allowed = allowable_adjustment_factor
            factor = max(min_factor_allowed, min(factor, max_factor_allowed))
    
        # 7. Log adjustment details
        target_duration = original_duration / factor
        logger.info(f"Applying speed factor of {factor:.2f} to VO")
        logger.debug(f"VO Duration : Original:{original_duration:.2f}s, Target:{target_duration:.2f}s")
        
        # 8. Apply speed adjustment using FFmpeg
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", format,
            "-i", "pipe:0",
            "-filter:a", f"atempo={factor}",
            "-f", format,
            "pipe:1"
        ]

        # 9. Run FFmpeg
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_data, stderr_data = proc.communicate(input=input_bytes)

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed with error:\n{stderr_data.decode('utf-8', errors='ignore')}")

        # 10. Yield processed audio
        chunk_size = 4096
        for i in range(0, len(stdout_data), chunk_size):
            yield stdout_data[i:i+chunk_size]

def normalize_audio(
    input_path: Path,
    output_path: Path,
    target_lufs: float = -23.0,
    fade_in_ms: float = 10.0
):
    """
    1) Loudness‑normalize to target_lufs (EBU R128)
    2) Apply a short fade‑in to mask any pop
    3) Write to a temp file, then replace output_path
    4) Suppress all FFmpeg logs unless there's an error
    """
    inp = str(input_path.expanduser().resolve())
    out = Path(output_path).expanduser().resolve()
    tmp = out.with_name(out.stem + ".normalized.tmp" + out.suffix)

    # build the filter graph as a single FFmpeg filter_complex string
    # loudnorm: i=integrated_LUFS, lra=loudness_range (you can tweak), tp=true_peak
    # afade: t=in, st=0 start at 0s, d=fade_in_ms/1000 seconds
    filter_chain = (
        f"loudnorm=i={target_lufs}:lra=7:tp=-1,"
        f"afade=t=in:st=0:d={fade_in_ms/1000.0}"
    )

    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",  # silence all non‑error logs
        "-y",                                   # overwrite output without asking
        "-i", inp,
        "-filter_complex", filter_chain,
        "-c:a", "pcm_s16le",                    # output codec (WAV/PCM)
        str(tmp)
    ]

    # run and capture stderr only
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore")
        logger.error(f"Normalization failed:\n{err}")
        raise RuntimeError(f"Normalization failed:\n{err}")

    # atomically replace the original file
    tmp.replace(out)
    logger.info(f"✔ Normalized & faded in '{inp}' → '{out}'")

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", type=str, required=True)
    parser.add_argument("--output_path", type=str, required=True)
    args = parser.parse_args()

    normalize_audio(args.input_path, args.output_path)

if __name__ == "__main__":
    main()
