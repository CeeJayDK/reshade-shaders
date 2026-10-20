#!/usr/bin/env python3
"""Checks the EffectFiles list of every package in EffectPackages.ini against the effects in its download.

  effect_files.py EffectPackages.ini REPORT.md

Each package's DownloadUrl is read the way ReShade's setup installs it (setup/MainWindow.xaml.cs): the archive's first
folder named Shaders, else the shortest folder holding an .fx file, and every .fx file below it, minus DenyEffectFiles.
EffectFiles is then corrected in place: names no longer in the download are removed, names only in the download are
added at the end (sorted), names that differ only in case take the download's spelling. Everything else in the file is
left as it is. A package whose download fails is left unchanged and listed in the report.
"""
import io, os, re, sys, tempfile, urllib.request, zipfile


def shaders_dir(root):
    found = []
    for d, _, files in os.walk(root):
        if os.path.basename(d).lower() == "shaders":
            found.append((0, d.count(os.sep), d))
        elif any(f.lower().endswith(".fx") for f in files):
            found.append((1, len(d), d))
    return min(found)[2] if found else None


def effects_in(url):
    data = urllib.request.urlopen(url, timeout=120).read()
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)  # zipfile drops absolute and .. paths
        src = shaders_dir(tmp)
        if not src:
            raise RuntimeError("no Shaders folder and no .fx file in the download")
        return {f for _, _, files in os.walk(src) for f in files if f.lower().endswith(".fx")}


def split(value):
    return [f.strip() for f in value.split(",") if f.strip()]


def corrected(listed, found):
    by_lower = {f.lower(): f for f in found}
    keep, seen = [], set()
    for f in listed:
        real = by_lower.get(f.lower())
        if real and real.lower() not in seen:
            keep.append(real)
            seen.add(real.lower())
    added = sorted((f for f in found if f.lower() not in seen), key=str.lower)
    return keep + added


def main(ini, report):
    lines = open(ini, "rb").read().decode("utf-8-sig").splitlines(keepends=True)
    sections = []  # (name, {key: line index})
    for i, line in enumerate(lines):
        if line.startswith("["):
            sections.append((line.strip(), {}))
        elif sections and "=" in line:
            sections[-1][1][line.split("=", 1)[0].strip()] = i
    value = lambda i: lines[i].split("=", 1)[1].rstrip("\r\n")
    rows, failed = [], []
    for name, keys in sections:
        if "DownloadUrl" not in keys or "EffectFiles" not in keys:
            continue
        title = value(keys["PackageName"]) if "PackageName" in keys else name
        try:
            found = effects_in(value(keys["DownloadUrl"]))
        except Exception as e:  # one broken download must not stop the others
            failed.append(f"- {name} {title}: {e}")
            continue
        deny = {f.lower() for f in split(value(keys["DenyEffectFiles"]))} if "DenyEffectFiles" in keys else set()
        found = {f for f in found if f.lower() not in deny}
        i = keys["EffectFiles"]
        listed = split(value(i))
        new = corrected(listed, found)
        if new != listed:
            end = lines[i][len(lines[i].rstrip("\r\n")):]
            lines[i] = "EffectFiles=" + ",".join(new) + end
            old_l = {f.lower() for f in listed}
            new_l = {f.lower() for f in new}
            gone = [f for f in listed if f.lower() not in new_l]
            came = [f for f in new if f.lower() not in old_l]
            case = [f for f in new if f.lower() in old_l and f not in listed]
            parts = ([f"removed {', '.join(gone)}"] if gone else []) + ([f"added {', '.join(came)}"] if came else []) + \
                    ([f"spelling {', '.join(case)}"] if case else [])
            rows.append(f"- {name} {title}: " + "; ".join(parts))
        print(f"{name} {title}: {len(found)} effects", flush=True)
    open(ini, "wb").write("".join(lines).encode("utf-8"))
    md = "EffectFiles checked against each package's download (as ReShade's setup installs it).\n\n"
    md += ("### Changed\n" + "\n".join(rows) + "\n\n") if rows else "No changes.\n\n"
    if failed:
        md += "### Download failed (left unchanged)\n" + "\n".join(failed) + "\n"
    open(report, "w", encoding="utf-8").write(md)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    # Self-check of the list rule: case fix, removal, addition at the end.
    assert corrected(["B.fx", "a.FX", "Gone.fx"], {"a.fx", "B.fx", "C.fx"}) == ["B.fx", "a.fx", "C.fx"]
    main(sys.argv[1], sys.argv[2])
