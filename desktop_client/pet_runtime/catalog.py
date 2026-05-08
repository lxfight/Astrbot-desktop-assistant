"""Pet package discovery and import helpers."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PETS_DIR = PACKAGE_ROOT / "assets" / "pets"


@dataclass(frozen=True)
class PetPackage:
    """A local Codex-compatible pet package."""

    id: str
    display_name: str
    description: str
    package_dir: Path
    manifest_path: Path
    spritesheet_path: Path
    manifest: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "displayName": self.display_name,
            "description": self.description,
            "manifestPath": str(self.manifest_path),
            "spritesheetPath": str(self.spritesheet_path),
            "builtin": self.package_dir.is_relative_to(BUILTIN_PETS_DIR)
            if hasattr(self.package_dir, "is_relative_to")
            else str(self.package_dir).startswith(str(BUILTIN_PETS_DIR)),
        }


class PetCatalog:
    """Loads bundled and user-imported Codex-compatible pet packages."""

    def __init__(
        self,
        builtin_dir: Path = BUILTIN_PETS_DIR,
        user_dir: Optional[Path] = None,
    ):
        self.builtin_dir = Path(builtin_dir)
        self.user_dir = Path(user_dir) if user_dir else None
        self._pets: dict[str, PetPackage] = {}
        self.refresh()

    def refresh(self) -> None:
        pets: dict[str, PetPackage] = {}
        for root in [self.builtin_dir, self.user_dir]:
            if not root or not root.exists():
                continue
            for manifest in sorted(root.glob("*/pet.json")):
                pet = self.load_package(manifest.parent)
                pets[pet.id] = pet
        self._pets = pets

    @property
    def pets(self) -> dict[str, PetPackage]:
        return dict(self._pets)

    def get(self, pet_id: str) -> Optional[PetPackage]:
        return self._pets.get(pet_id)

    def default_pet(self, preferred_id: str = "taotao") -> PetPackage:
        pet = self.get(preferred_id)
        if pet:
            return pet
        if not self._pets:
            raise FileNotFoundError("No pet packages are available")
        return next(iter(self._pets.values()))

    @staticmethod
    def resolve_package_dir(source: str | Path) -> Path:
        path = Path(source).expanduser()
        if path.is_file():
            if path.name == "pet.json":
                return path.parent
            if path.name == "spritesheet.webp":
                return path.parent
        return path

    @classmethod
    def load_package(cls, source: str | Path) -> PetPackage:
        package_dir = cls.resolve_package_dir(source)
        manifest_path = package_dir / "pet.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"pet.json not found: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        pet_id = str(manifest.get("id") or package_dir.name).strip()
        if not pet_id:
            raise ValueError("Pet package id is empty")

        spritesheet_name = manifest.get("spritesheetPath", "spritesheet.webp")
        spritesheet_path = (package_dir / spritesheet_name).resolve()
        if not spritesheet_path.exists():
            raise FileNotFoundError(f"spritesheet not found: {spritesheet_path}")

        return PetPackage(
            id=pet_id,
            display_name=str(manifest.get("displayName") or pet_id),
            description=str(manifest.get("description") or ""),
            package_dir=package_dir.resolve(),
            manifest_path=manifest_path.resolve(),
            spritesheet_path=spritesheet_path,
            manifest=manifest,
        )

    def import_local(
        self,
        source: str | Path,
        force: bool = False,
        pet_id: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> PetPackage:
        if not self.user_dir:
            raise ValueError("User pet package directory is not configured")

        source_package = self.load_package(source)
        target_id = pet_id or source_package.id
        target_dir = self.user_dir / target_id
        if target_dir.exists() and not force:
            raise FileExistsError(f"Pet package already exists: {target_id}")

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_package.spritesheet_path, target_dir / "spritesheet.webp")

        manifest = {
            "id": target_id,
            "displayName": display_name or source_package.display_name,
            "description": description or source_package.description,
            "spritesheetPath": "spritesheet.webp",
        }
        with open(target_dir / "pet.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")

        self.refresh()
        imported = self.get(target_id)
        if not imported:
            raise RuntimeError(f"Imported pet package was not registered: {target_id}")
        return imported


def get_default_catalog(user_dir: Optional[Path] = None) -> PetCatalog:
    return PetCatalog(user_dir=user_dir)
