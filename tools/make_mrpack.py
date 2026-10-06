"""
Build the one-click install pack: dist/mc-eca-<version>.mrpack

An .mrpack (Modrinth modpack) can be imported in Prism Launcher and the Modrinth
App. It creates a separate Minecraft instance with the right Minecraft version,
Fabric Loader, Fabric API and MC-ECA, so students don't install Fabric by hand and
their other Minecraft installations stay untouched.

    python tools/make_mrpack.py          (after: cd mod && ./gradlew build)

Versions come from mod/gradle.properties. Fabric API is not copied into the pack:
the pack lists its official Modrinth download (with checksums), which is how
Modrinth packs work. Only Python's standard library is used.
"""

import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def properties():
    props = {}
    for line in (ROOT / "mod" / "gradle.properties").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    return props


def fetch(url, binary=False):
    request = urllib.request.Request(url, headers={"User-Agent": "mc-eca/make_mrpack (course tool)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    return data if binary else json.loads(data)


def fabric_api_file(minecraft, wanted_version):
    query = urllib.parse.urlencode({"game_versions": json.dumps([minecraft]), "loaders": json.dumps(["fabric"])})
    versions = fetch(f"https://api.modrinth.com/v2/project/fabric-api/version?{query}")
    for version in versions:
        if version["version_number"] == wanted_version:
            file = next(f for f in version["files"] if f["primary"])
            # Download once and check the hashes ourselves, so the pack can't point at a broken file.
            data = fetch(file["url"], binary=True)
            sha1, sha512 = hashlib.sha1(data).hexdigest(), hashlib.sha512(data).hexdigest()
            if sha1 != file["hashes"]["sha1"] or sha512 != file["hashes"]["sha512"] or len(data) != file["size"]:
                sys.exit(f"Fabric API download does not match Modrinth's checksums: {file['url']}")
            return file
    sys.exit(f"Fabric API {wanted_version} for Minecraft {minecraft} not found on Modrinth")


def main():
    props = properties()
    version = props["mod_version"]
    minecraft = props["minecraft_version"]
    jar = ROOT / "mod" / "build" / "libs" / f"mc-eca-{version}.jar"
    if not jar.exists():
        sys.exit(f"{jar} not found - build the mod first: cd mod && ./gradlew build")

    api = fabric_api_file(minecraft, props["fabric_api_version"])
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": version,
        "name": f"MC-ECA {version}",
        "summary": "Embodied conversational agents in Minecraft (Human-Agent Interaction course)",
        "files": [{
            "path": f"mods/{api['filename']}",
            "hashes": {"sha1": api["hashes"]["sha1"], "sha512": api["hashes"]["sha512"]},
            "env": {"client": "required", "server": "required"},
            "downloads": [api["url"]],
            "fileSize": api["size"],
        }],
        "dependencies": {"minecraft": minecraft, "fabric-loader": props["loader_version"]},
    }

    out = ROOT / "dist" / f"mc-eca-{version}.mrpack"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("modrinth.index.json", json.dumps(index, indent=2))
        z.write(jar, f"overrides/mods/{jar.name}")
        # The game keeps running while you click into your terminal/editor (no F3+P needed).
        z.writestr("overrides/options.txt", "pauseOnLostFocus:false\n")
    print(f"wrote {out.relative_to(ROOT)}  (Minecraft {minecraft}, Fabric Loader {props['loader_version']}, "
          f"{api['filename']}, {jar.name})")


if __name__ == "__main__":
    main()
