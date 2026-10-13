"""完整包发布；替换失败恢复旧版本。"""
from pathlib import Path
import shutil
import tempfile

def publish_package(candidate: Path, final_dir: Path) -> None:
    """发布完整包；替换失败时恢复旧版本。校验由调用方先完成。"""
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        # Unique backup names avoid clobbering another pending publication.
        backup = Path(tempfile.mkdtemp(prefix=f'.old_{final_dir.name}_', dir=final_dir.parent))
        backup.rmdir()
        final_dir.rename(backup)
        try:
            candidate.rename(final_dir)
        except BaseException:
            backup.rename(final_dir)
            raise
        else:
            shutil.rmtree(backup)
    else:
        candidate.rename(final_dir)

