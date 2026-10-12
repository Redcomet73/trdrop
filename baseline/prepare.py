"""Extract the frozen oracle. Instrument ONLY an expendable generated copy.

Every edit has an exact, unique anchor and is recorded in a reversible patch ledger.
The application in original/ is never edited. No kernel replacements or bug fixes.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

SOURCE = "a0b4563a076e336863f743ec92c1ee8221f5aba6"
SOURCE_TREE = "2759fa354d66adbc342c882d8f0faa390699bed4"


def git_bytes(repo, *arguments):
    return subprocess.check_output([
        "git", "--no-replace-objects", "-C", str(repo), *arguments
    ])


def expected_manifest(repo):
    commit = git_bytes(
        repo, "rev-parse", "--verify", SOURCE + "^{commit}"
    ).decode("ascii").strip()
    tree = git_bytes(
        repo, "rev-parse", "--verify", SOURCE + "^{tree}"
    ).decode("ascii").strip()
    if commit != SOURCE or tree != SOURCE_TREE:
        raise ValueError("Frozen commit/tree verification failed")

    files = {}
    entries = git_bytes(
        repo, "ls-tree", "-r", "-z", "--full-tree", SOURCE
    )
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        name = raw_path.decode("utf-8")
        path = Path(name)
        if (
            kind != "blob"
            or mode not in {"100644", "100755"}
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or ":" in name
        ):
            raise ValueError("Unsupported frozen tree entry: " + name)

        data = git_bytes(repo, "cat-file", "blob", object_id)
        files[name] = {
            "git_blob": object_id,
            "git_mode": mode,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    if not files:
        raise ValueError("Frozen source tree is empty")
    return {
        "schema": 2,
        "source_sha": SOURCE,
        "source_tree": SOURCE_TREE,
        "files": files,
    }


def verify_original(original, expected):
    if original.is_symlink() or not original.is_dir():
        raise ValueError("Invalid original source directory")

    actual = {}
    for path in original.rglob("*"):
        if path.is_symlink():
            raise ValueError("Unexpected source symlink: " + str(path))
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Unexpected source entry: " + str(path))
        name = path.relative_to(original).as_posix()
        data = path.read_bytes()
        actual[name] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    if set(actual) != set(expected["files"]):
        raise ValueError("Frozen file inventory mismatch")
    for name, record in expected["files"].items():
        if actual[name] != {
            "size": record["size"],
            "sha256": record["sha256"],
        }:
            raise ValueError("Frozen source bytes differ: " + name)


def instrument(edit, read_text):
    """The approved insertion recipe, shared by preparation and verification."""
    for path,cls in [('headers/cpp_interface/frameprocessing.h','FrameProcessing'),
                     ('headers/cpp_interface/tearmodel.h','TearModel'),
                     ('headers/qml_interface/frameprocessing_qml.h','FrameProcessingQML'),
                     ('headers/qml_interface/renderer_qml.h','RendererQML')]:
        text=read_text(path)
        start=text.index('class '+cls)
        brace=text.index('{',start)
        anchor=text[start:brace+1]
        edit(path,anchor,anchor+'\n    friend struct BaselineProbe;\n')

    f='headers/cpp_interface/frameprocessing.h'
    edit(f,'#include <QDebug>','#include <QDebug>\n#include "telemetry.h"')
    edit(f,'const quint32 pixel_difference =',
         'BASE_VIDEO(i);\n                    const quint32 pixel_difference =')
    edit(f,'QList<double> framerates;','BASE_SCOPE(fps_clock, fps_frametime);\n        QList<double> framerates;')
    edit(f,'QList<double> frametimes;','BASE_SCOPE(ft_clock, fps_frametime);\n        QList<double> frametimes;')
    edit(f,'cv::Mat black_white_frame_a;', 'BASE_SCOPE(gray_clock, grayscale);\n        cv::Mat black_white_frame_a;')
    end='cv::cvtColor(frame_b, black_white_frame_b, cv::COLOR_BGRA2GRAY);'
    edit(f,end,end+'\n        BASE_STOP(gray_clock);\n        BASE_GRAY(black_white_frame_a, black_white_frame_b);\n        BASE_SCOPE(mask_clock, mask);')
    edit(f,'const std::vector<double> row_differences = _get_row_differences(difference);',
         'const std::vector<double> row_differences = _get_row_differences(difference);\n        BASE_SCOPE(tear_clock, tear);')
    edit(f,'std::vector<double> row_differences(static_cast<size_t>(difference.rows), 0.0);',
         'BASE_SCOPE(row_clock, rows);\n        std::vector<double> row_differences(static_cast<size_t>(difference.rows), 0.0);')
    edit(f,'return row_differences;',
         'BASE_STOP(row_clock);\n        BASE_ROWS(difference, row_differences);\n        return row_differences;')
    edit(f,'if (found_different_pixel) return 1.0;\n                else return 0.0;',
         'if (found_different_pixel) return BASE_RETURN("dismiss_full", 1.0);\n                else return BASE_RETURN("dismiss_zero", 0.0);')
    edit(f,'} else return 1 - max_tear_percentage;',
         '} else return BASE_RETURN("fractional", 1 - max_tear_percentage);')
    edit(f,'if (found_different_pixel && tear_not_found) return 1.0;',
         'if (found_different_pixel && tear_not_found) return BASE_RETURN("no_tear_full", 1.0);')
    edit(f,'return 0.0;\n    }\n    //! returns the percentage',
         'return BASE_RETURN("no_tear_zero", 0.0);\n    }\n    //! returns the percentage')

    # Slot timers stop before signals: otherwise downstream direct slots are double-counted.
    for path,anchor,stage,emit in [
        ('headers/qml_interface/imageconverter_qml.h','_prepare_image_list(cv_image_list.size());','conversion','emit imagesReady(_qml_image_list);'),
        ('headers/qml_interface/imagecomposer_qml.h','QSize _size = _shared_resolution_model->get_active_value().size();','composition','emit imageReady(_qml_image);'),
        ('headers/qml_interface/renderer_qml.h','if (qml_image.isNull()) return;','rendering','emit imageReady(qml_image);')]:
        edit(path,'#include <QObject>' if stage!='rendering' else '#include <QtQuick/QQuickPaintedItem>',
             ('#include <QObject>' if stage!='rendering' else '#include <QtQuick/QQuickPaintedItem>')+'\n#include "telemetry.h"')
        # composer has another QSize _size in cropping; use the following branch for uniqueness.
        if stage=='composition':anchor+='\n\n        if (_qml_image_list.size() == 3)'
        edit(path,anchor,'BASE_SCOPE(stage_clock, '+stage+');\n        '+anchor)
        if stage=='composition':emit+='\n    }\n    //! if the resolution changes'
        edit(path,emit,'BASE_STOP(stage_clock);\n        '+emit)
    path='headers/cpp_interface/videocapturelist.h'
    edit(path,'#include <QDebug>','#include <QDebug>\n#include "telemetry.h"')
    edit(path,'if (_container_sizes_not_matched()) _prepare_frame_lists();',
         'BASE_SCOPE(decode_clock, decode);\n        if (_container_sizes_not_matched()) _prepare_frame_lists();')
    path='headers/qml_interface/exporter_qml.h'
    edit(path,'#include <QObject>','#include <QObject>\n#include "telemetry.h"')
    edit(path,'QString filepath = _create_image_file_path();','BASE_SCOPE(image_clock, image_export);\n                QString filepath = _create_image_file_path();')
    edit(path,'_append_framerates();','BASE_SCOPE(csv_clock, csv_export);\n                _append_framerates();')

def verify_observed(dest, expected, manifest):
    """Reconstruct the approved edits independently from verified frozen files."""
    original = dest / "original"
    texts = {}
    ledger = []

    def read_text(path):
        name = "trdrop/" + path
        if name not in expected["files"]:
            raise ValueError("Instrumentation path is outside frozen files: " + path)
        if path not in texts:
            texts[path] = (original / name).read_text(encoding="utf-8-sig")
        return texts[path]

    def edit(path, old, new):
        text = read_text(path)
        if text.count(old) != 1:
            raise ValueError("Verification anchor is not unique: " + path)
        texts[path] = text.replace(old, new)
        ledger.append(dict(path=path, old=old, new=new))

    instrument(edit, read_text)
    if manifest.get("edits") != ledger:
        raise ValueError("Instrumentation ledger differs from approved recipe")

    files = dict(expected["files"])
    for path, text in texts.items():
        # Generated edits use UTF-8 without BOM and LF on every host.
        data = text.encode("utf-8")
        files["trdrop/" + path] = {
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest()
        }
    telemetry = Path(__file__).with_name("telemetry.h").read_bytes()
    files["trdrop/telemetry.h"] = {
        "size": len(telemetry), "sha256": hashlib.sha256(telemetry).hexdigest()
    }
    verify_original(dest / "observed", {"files": files})


def verify(repo, dest):
    repo = Path(repo).resolve()
    dest = Path(dest).resolve()
    expected = expected_manifest(repo)
    manifest = json.loads(
        (dest / "source-manifest.json").read_text(encoding="utf-8")
    )
    for field in ("schema", "source_sha", "source_tree", "files"):
        if manifest.get(field) != expected[field]:
            raise ValueError("Frozen manifest mismatch: " + field)
    verify_original(dest / "original", expected)
    verify_observed(dest, expected, manifest)


def prepare(repo, dest):
    repo = Path(repo).resolve()
    dest = Path(dest).resolve()
    expected = expected_manifest(repo)

    dest.mkdir(parents=True, exist_ok=False)
    archive = git_bytes(repo, "archive", "--format=tar", SOURCE)
    original = dest / "original"
    original.mkdir()

    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            if (
                not (member.isfile() or member.isdir())
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or ":" in member.name
            ):
                raise ValueError("Unsafe archive entry: " + member.name)
        tar.extractall(original, filter="data")

    verify_original(original, expected)

    generated = dest / "observed"
    shutil.copytree(original, generated)
    shutil.copy2(
        Path(__file__).with_name("telemetry.h"),
        generated / "trdrop" / "telemetry.h",
    )
    ledger = []

    def edit(path,old,new):
        file=generated/'trdrop'/path
        text=file.read_text(encoding='utf-8-sig')
        if text.count(old)!=1:
            raise ValueError(f'Anchor count {text.count(old)}: {path}: {old}')
        file.write_text(text.replace(old,new),encoding='utf-8',newline='\n')
        ledger.append(dict(path=path,old=old,new=new))

    instrument(edit, lambda path: (generated/'trdrop'/path).read_text())

    # Verify reverse edits recover the frozen text exactly (apart from BOM/newline encoding).
    for path in {e['path'] for e in ledger}:
        recovered=(generated/'trdrop'/path).read_text(encoding='utf-8-sig')
        for e in reversed([x for x in ledger if x['path']==path]):
            if recovered.count(e['new'])!=1:raise ValueError('Non-reversible instrumentation')
            recovered=recovered.replace(e['new'],e['old'])
        if recovered!=(original/'trdrop'/path).read_text(encoding='utf-8-sig'):
            raise ValueError('Original expression changed: '+path)
    verify_original(original, expected)
    manifest = dict(expected)
    manifest["edits"] = ledger
    (dest / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    verify(repo, dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("repository")
    parser.add_argument("output")
    arguments = parser.parse_args()
    if arguments.verify:
        verify(arguments.repository, arguments.output)
    else:
        prepare(arguments.repository, arguments.output)
