"""UI Components — Rich renderers cho Human Review CLI."""

from __future__ import annotations

import textwrap

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

console = Console()

# ── Color constants ─────────────────────────────────────────────────────────
COLOR_EASY = "green"
COLOR_MEDIUM = "yellow"
COLOR_HARD = "red"
COLOR_LABEL_0 = "green"
COLOR_LABEL_1 = "red"
COLOR_MODEL_A = "cyan"
COLOR_MODEL_B = "magenta"
COLOR_ACCENT = "blue"


# ── Render functions ────────────────────────────────────────────────────────


def render_header(reviewer_id: str, batch_idx: int, record_idx: int, total: int,
                  difficulty: str) -> None:
    """Render header bar."""
    tier_color = {
        "easy": COLOR_EASY,
        "medium": COLOR_MEDIUM,
        "hard": COLOR_HARD,
    }.get(difficulty, "white")

    header = Text()
    header.append(f"REVIEWER: ", style="bold")
    header.append(f"{reviewer_id}", style=f"bold {COLOR_ACCENT}")
    header.append(f" | RECORD ", style="bold")
    header.append(f"{record_idx + 1}", style="bold")
    header.append(f" / {total}", style="bold")
    header.append(f" | ", style="bold")
    header.append(f"{difficulty.upper()}", style=f"bold {tier_color}")

    console.print(Panel(header, padding=(0, 1), expand=True))


def render_headline(title: str, source: str, url: str) -> None:
    """Render headline + source info."""
    console.print()
    console.print("[bold]TIÊU ĐỀ:[/bold]")
    # Word wrap long titles
    wrapped = textwrap.fill(title, width=console.width - 4)
    console.print(Panel(wrapped, padding=(0, 2), border_style=COLOR_ACCENT))
    console.print(f"[dim]Nguồn: {source} | URL: {url}[/dim]")
    console.print()


def render_sapo(sapo: str) -> None:
    """Render sapo (tóm tắt)."""
    if not sapo:
        return
    console.print("[bold]SAPO (TÓM TẮT):[/bold]")
    wrapped = textwrap.fill(sapo, width=console.width - 4)
    console.print(Panel(wrapped, padding=(0, 2), border_style="grey50"))


def render_model_outputs(record: dict) -> None:
    """Render LLM predictions từ 2 models."""
    ma_label = record.get("model_a_label")
    ma_conf = record.get("model_a_confidence", 0)
    ma_rubric = record.get("model_a_rubric_scores", [])
    ma_reason = record.get("model_a_reason", "")
    mb_label = record.get("model_b_label")
    mb_conf = record.get("model_b_confidence", 0)
    mb_rubric = record.get("model_b_rubric_scores", [])
    mb_reason = record.get("model_b_reason", "")

    agree = "✅ AGREE" if ma_label == mb_label else "⚠️  DISAGREE"

    # Build table for side-by-side comparison
    table = Table(
        show_header=True,
        header_style="bold",
        expand=True,
        box=None,
        padding=(0, 1),
    )
    table.add_column(f"Qwen 2.5 3B [{COLOR_MODEL_A}]", style=COLOR_MODEL_A)
    table.add_column(f"Gemma 2 2B [{COLOR_MODEL_B}]", style=COLOR_MODEL_B)

    # Prediction row
    ma_pred = "CLICKBAIT" if ma_label == 1 else "NON-CLICKBAIT"
    mb_pred = "CLICKBAIT" if mb_label == 1 else "NON-CLICKBAIT"
    table.add_row(
        f"Pred: {ma_pred} (conf: {ma_conf:.2f})",
        f"Pred: {mb_pred} (conf: {mb_conf:.2f})",
    )

    # Rubric row
    ma_r = " ".join(str(s) for s in (ma_rubric or [0, 0, 0, 0]))
    mb_r = " ".join(str(s) for s in (mb_rubric or [0, 0, 0, 0]))
    table.add_row(
        f"Rubric [C1-C4]: {ma_r} → total={sum(ma_rubric or [0,0,0,0])}",
        f"Rubric [C1-C4]: {mb_r} → total={sum(mb_rubric or [0,0,0,0])}",
    )

    # Reason row (truncate if too long)
    ma_short = (ma_reason or "")[:80] + ("..." if len(ma_reason or "") > 80 else "")
    mb_short = (mb_reason or "")[:80] + ("..." if len(mb_reason or "") > 80 else "")
    table.add_row(ma_short, mb_short)

    console.print()
    console.print(f"[bold]MODELS:[/bold] {agree}")
    console.print(table)


def render_rubric_prompt() -> None:
    """Render rubric scoring prompt."""
    console.print()
    console.print("[bold]RUBRIC BARS[/bold] — đánh giá tiêu đề (0-2 mỗi tiêu chí):")
    console.print("  [cyan]C1[/cyan] Phóng đại cảm xúc: 0=trung lập, 1=cảm xúc phổ thông, 2=kích động mạnh/cực đoan")
    console.print("  [cyan]C2[/cyan] Khoảng trống TT:   0=đủ chủ thể+kết quả, 1=thiếu chi tiết phụ, 2=cắt đứt TT cốt lõi")
    console.print("  [cyan]C3[/cyan] Định khung cú pháp: 0=khẳng định chuẩn, 1=hỏi mở/cảm thán nhẹ, 2=mệnh lệnh/áp đặt/khiêu khích")
    console.print("  [cyan]C4[/cyan] Bất tương đồng:    0=khớp Sapo/bài, 1=nhấn chi tiết phụ, 2=mâu thuẫn/không có trong bài")
    console.print()


def render_label_prompt() -> None:
    """Render label selection prompt."""
    console.print("[bold]LABEL:[/bold]")
    console.print("  [green][0][/green] Non-clickbait", end="")
    console.print("      [red][1][/red] Clickbait")
    console.print()


def render_shortcuts() -> None:
    """Render keyboard shortcuts reminder."""
    console.print()
    console.print("[dim]Phím tắt: [Enter] Xác nhận | [S] Bỏ qua | [P] Trước | [N] Tiếp | [Q] Lưu & thoát | [?] Rubric reminder[/dim]")


def render_progress(completed: int, total: int, skipped: int) -> None:
    """Render progress bar."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("• {task.fields[skipped]} skipped"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            "Reviewing",
            total=total,
            completed=completed,
            skipped=f"[yellow]{skipped}[/yellow]",
        )


def render_review_stats(stats: dict) -> None:
    """Render summary statistics."""
    table = Table(title="📊 Thống kê", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Giá trị", justify="right")

    table.add_row("Đã review", str(stats.get("completed", 0)))
    table.add_row("Bỏ qua", str(stats.get("skipped", 0)))
    table.add_row("Còn lại", str(stats.get("remaining", 0)))
    table.add_row("Thời gian TB/record", f"{stats.get('avg_time', 0):.1f}s")
    table.add_row("Clickbait rate", f"{stats.get('cb_rate', 0):.1%}")
    table.add_row("Non-clickbait rate", f"{stats.get('non_cb_rate', 0):.1%}")

    console.print()
    console.print(table)


def render_completion_message(stats: dict) -> None:
    """Render completion message."""
    console.print()
    console.print(
        Panel(
            f"[bold green]✓ Hoàn thành![/bold green]\n\n"
            f"Đã review: {stats.get('completed', 0)} records\n"
            f"Bỏ qua: {stats.get('skipped', 0)} records\n"
            f"Thời gian: {stats.get('total_time', 0):.0f}s\n"
            f"Output: {stats.get('output_path', '')}",
            title="Phase 6 — Human Review Complete",
            border_style="green",
        )
    )


def render_help() -> None:
    """Render rubric reminder help."""
    help_text = (
        "[bold]Rubric BARS (0-2 điểm/tiêu chí):[/bold]\n"
        "  [cyan]C1[/cyan] — Phóng đại cảm xúc:\n"
        "    0 = Trung lập, trình bày khách quan\n"
        "    1 = Cảm xúc phổ thông để tăng hấp dẫn (ngỡ ngàng, nóng...)\n"
        "    2 = Kích động mạnh, thổi phồng cực đoan (sốc tận óc, ngã ngửa...)\n"
        "  [cyan]C2[/cyan] — Khoảng trống thông tin:\n"
        "    0 = Cấu trúc đầy đủ chủ thể + hành động + kết quả chính\n"
        "    1 = Ẩn chi tiết phụ (thời gian, địa điểm...) để tạo tò mò nhẹ\n"
        "    2 = Cố ý cắt đứt thông tin cốt lõi bằng từ lửng lơ/vô định\n"
        "  [cyan]C3[/cyan] — Định khung cú pháp:\n"
        "    0 = Câu khẳng định/truy vấn thông tin chuẩn mực\n"
        "    1 = Câu hỏi gợi mở nhẹ hoặc cảm thán ngắn\n"
        "    2 = Mệnh lệnh trực tiếp, áp đặt hành vi hoặc tu từ khiêu khích\n"
        "  [cyan]C4[/cyan] — Tính bất tương đồng:\n"
        "    0 = Khớp hoàn toàn với nội dung Sapo/thân bài viết\n"
        "    1 = Hơi nhấn quá đà chi tiết phụ hoặc trích dẫn gián tiếp\n"
        "    2 = Mâu thuẫn trực tiếp, hoàn toàn không có trong bài viết\n"
        "\n[bold]Label:[/bold] Tổng C1+C2+C3+C4 >= 4 → Clickbait (1), < 4 → Non-clickbait (0)"
    )
    console.print(Panel(help_text, title="📖 Rubric BARS Hướng Dẫn", border_style=COLOR_ACCENT))
