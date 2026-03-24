import asyncio
import shutil
from pathlib import Path


async def compile_latex(main_tex: Path, job_id: str) -> tuple[Path, str]:
    """Compile main.tex with XeLaTeX (runs twice for cross-references).

    Returns (output_pdf_path, log_text).
    Raises RuntimeError if compilation fails fatally.
    """
    work_dir = main_tex.parent
    log_lines = []

    for run in range(2):
        proc = await asyncio.create_subprocess_exec(
            "xelatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            str(main_tex.name),
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        log_text = stdout.decode(errors="replace")
        log_lines.append(f"=== XeLaTeX run {run + 1} ===\n{log_text}")

        if proc.returncode != 0 and run == 0:
            # First run failure — check if PDF was partially produced
            pdf_candidate = work_dir / "main.pdf"
            if not pdf_candidate.exists():
                raise RuntimeError(
                    f"XeLaTeX failed (exit {proc.returncode}).\n"
                    + _extract_errors(log_text)
                )

    full_log = "\n".join(log_lines)

    # Rename output PDF
    src_pdf = work_dir / "main.pdf"
    if not src_pdf.exists():
        raise RuntimeError(
            "XeLaTeX did not produce main.pdf.\n" + _extract_errors(full_log)
        )

    dest_pdf = work_dir / f"{job_id}_translated.pdf"
    shutil.move(str(src_pdf), str(dest_pdf))

    return dest_pdf, full_log


def _extract_errors(log: str) -> str:
    """Extract error lines from XeLaTeX log."""
    lines = log.splitlines()
    errors = [l for l in lines if l.startswith("!") or "Error" in l]
    return "\n".join(errors[:20]) if errors else log[-1000:]
