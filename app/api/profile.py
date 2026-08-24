"""简历/JD 资料端点 —— 模拟面试三源出题的数据源（data/resume.md、data/jd.md）。

模拟面试三源出题（简历 + JD + 错题）里，简历/JD 是静态文件。本模块把
「手动贴」升级为「上传文件自动提取」，简历与 JD 共用同一套解析逻辑：

- GET  /api/profile          → 简历/JD 状态：是否提供、来源文件名、更新时间、内容摘要
- POST /api/profile/resume   → 上传简历：.pdf(pypdf) / .txt / .md → 备份旧文件 → 写 data/resume.md
- POST /api/profile/jd       → 上传 JD：同上 → 写 data/jd.md

约束：PDF 只收文字版（扫描件提取不到文字返回 422）；txt/md 要求 UTF-8 编码。
覆盖前自动备份为 *.bak，来源文件名与字数记在 *.meta.json 侧车文件（供 UI 展示，不污染文档本身）。
"""
import io
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from src.config import space_dir

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

MAX_BYTES = 10 * 1024 * 1024  # 10MB 上限

SUPPORTED_EXT = (".pdf", ".txt", ".md", ".markdown")

router = APIRouter()

_RESUME_HEADER = (
    "# 个人简历（OfferLoop 面试官出题依据）\n\n"
    "> 由上传的文件自动提取（{filename}，{ts}）。\n"
    "> 这份简历会喂给模拟面试的 LLM，面试官会据此深挖你的项目（追问实现细节/难点/取舍）。\n\n"
)

_JD_HEADER = (
    "# 目标 JD（OfferLoop 面试官出题依据）\n\n"
    "> 由上传的文件自动提取（{filename}，{ts}）。\n"
    "> 这份 JD 会喂给模拟面试的 LLM，生成「JD 能力」验证章节。\n\n"
)


class DocStatus(BaseModel):
    provided: bool
    filename: str | None   # 来源文件名（meta 侧车；没有则回退 doc.md）
    updated_at: str | None  # ISO 时间，未提供为 None
    chars: int
    summary: str            # 正文前 60 字（跳过注释头），供 UI 防错展示


class ProfileResponse(BaseModel):
    resume: DocStatus
    jd: DocStatus


class UploadResponse(BaseModel):
    ok: bool
    kind: str              # resume / jd
    filename: str
    pages: int             # PDF 页数；txt/md 为 0
    chars: int
    backup_kept: bool


def _doc_path(name: str, space: str | None = None) -> Path:
    """per-space 优先，fallback 到 data/ 根目录（向后兼容）。"""
    if space:
        p = space_dir(space) / f"{name}.md"
        if p.exists():
            return p
    return DATA_DIR / f"{name}.md"


def _backup_path(name: str, space: str | None = None) -> Path:
    """备份放在同一目录（per-space 则入空间目录，否则根目录）。"""
    if space:
        return space_dir(space) / f"{name}.md.bak"
    return DATA_DIR / f"{name}.md.bak"


def _meta_path(name: str, space: str | None = None) -> Path:
    if space:
        return space_dir(space) / f"{name}.meta.json"
    return DATA_DIR / f"{name}.meta.json"


def _extract_text(data: bytes, filename: str) -> tuple[str, int]:
    """按扩展名提取文本，返回 (text, pages_or_0)。提取失败抛 ValueError(原因)。"""
    low = filename.lower()
    if low.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise HTTPException(status_code=500, detail="服务端缺 pypdf，请先安装（pip install pypdf）")
        reader = PdfReader(io.BytesIO(data))
        pages = max(len(reader.pages), 1)
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if not text:
            raise ValueError("empty_pdf")
        return text, pages
    if low.endswith(SUPPORTED_EXT[1:]):
        try:
            return data.decode("utf-8").strip(), 0
        except UnicodeDecodeError:
            raise ValueError("encoding")
    raise ValueError("unsupported")


def _write_doc(name: str, text: str, filename: str, pages: int, header: str, *, space: str | None = None) -> bool:
    """写文档（头注释 + 正文）+ meta 侧车。返回是否备份了旧文件。"""
    backup_kept = False
    # 传入 space → 写入 per-space；不传 → 写入 data/ 根目录（向后兼容）
    target_dir = space_dir(space) if space else DATA_DIR
    path = target_dir / f"{name}.md"
    if path.is_file():
        import shutil

        shutil.copy2(path, _backup_path(name, space=space))
        backup_kept = True

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    path.write_text(header.format(filename=filename, ts=ts) + text + "\n", encoding="utf-8")
    _meta_path(name, space=space).write_text(
        json.dumps({"filename": filename, "chars": len(text)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return backup_kept


def _summary(path: Path, limit: int = 60) -> str:
    """正文摘要：跳过注释头（# 和 > 开头的行），取首个非注释行的前 limit 字。"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith(("#", ">")):
                continue
            return s[:limit]
    except Exception:
        pass
    return ""


def _status(name: str, space: str | None = None) -> DocStatus:
    """per-space 优先。非 default 空间不 fallback（新空间显示空）。"""
    paths = []
    if space:
        paths.append(space_dir(space) / f"{name}.md")
    # 只有 default/未指定才 fallback 到 data/ 根目录（向后兼容已有用户）
    if space is None or space == "default":
        paths.append(DATA_DIR / f"{name}.md")

    for path in paths:
        if path.is_file():
            st = path.stat()
            meta = {}
            try:
                meta_p = _meta_path(name, space=space) if space else _meta_path(name)
                if meta_p.exists():
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                pass
            return DocStatus(
                provided=True,
                filename=meta.get("filename") or f"{name}.md",
                updated_at=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                chars=meta.get("chars", st.st_size),
                summary=_summary(path),
            )
    return DocStatus(provided=False, filename=None, updated_at=None, chars=0, summary="")


def _upload_doc(name: str, file: UploadFile, header: str, *, space: str | None = None) -> UploadResponse:
    filename = file.filename or f"{name}.txt"
    if not filename.lower().endswith(SUPPORTED_EXT):
        raise HTTPException(status_code=422, detail="只支持 PDF / .txt / .md 文件")

    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")

    try:
        text, pages = _extract_text(data, filename)
    except ValueError as e:
        if str(e) == "empty_pdf":
            raise HTTPException(
                status_code=422,
                detail="PDF 里没提取到文字——可能是扫描件/图片型 PDF。请换文字版（可先在浏览器 Ctrl+A 验证）",
            )
        if str(e) == "encoding":
            raise HTTPException(status_code=422, detail="文件不是 UTF-8 编码，请另存为 UTF-8 后重试")
        raise HTTPException(status_code=422, detail="不支持的文件类型")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败：{e}") from e

    backup_kept = _write_doc(name, text, filename, pages, header, space=space)
    return UploadResponse(ok=True, kind=name, filename=filename, pages=pages, chars=len(text), backup_kept=backup_kept)


@router.get("/profile", response_model=ProfileResponse)
def get_profile(space: str = "default"):
    """按空间查简历/JD 状态。"""
    return ProfileResponse(resume=_status("resume", space=space), jd=_status("jd", space=space))


@router.post("/profile/resume", response_model=UploadResponse)
def upload_resume(file: UploadFile, space: str = "default"):
    """上传简历到当前空间（PDF/txt/md）→ 提取文本 → 备份旧版 → 写 data/spaces/{space}/resume.md。"""
    return _upload_doc("resume", file, _RESUME_HEADER, space=space)


@router.post("/profile/jd", response_model=UploadResponse)
def upload_jd(file: UploadFile, space: str = "default"):
    """上传 JD 到当前空间（PDF/txt/md）→ 提取文本 → 备份旧版 → 写 data/spaces/{space}/jd.md。"""
    return _upload_doc("jd", file, _JD_HEADER, space=space)
