import importlib.util
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMPL_PATH = ROOT / "local_scripts" / "seed_domain_owners_impl.py"


def _missing_impl_message() -> str:
    return (
        f"missing local AI4S owner implementation: {LOCAL_IMPL_PATH}. "
        "This repo keeps AI4S owner accounts and seed details in a local ignored directory."
    )


def _load_local_module():
    if not LOCAL_IMPL_PATH.exists():
        raise RuntimeError(_missing_impl_message())
    spec = importlib.util.spec_from_file_location(
        "local_seed_domain_owners_impl",
        LOCAL_IMPL_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load local implementation from {LOCAL_IMPL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LOCAL_MODULE = _load_local_module()
__all__ = [name for name in dir(_LOCAL_MODULE) if not name.startswith("_")]
globals().update({name: getattr(_LOCAL_MODULE, name) for name in __all__})


if __name__ == "__main__":
    if not LOCAL_IMPL_PATH.exists():
        raise SystemExit(_missing_impl_message())
    runpy.run_path(str(LOCAL_IMPL_PATH), run_name="__main__")
