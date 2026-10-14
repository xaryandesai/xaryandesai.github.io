"""Prepare only public website files for GitHub Pages deployment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from build import ROOT, Renderer, safe_url

ASSET_SUFFIXES = {'.css', '.js', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.ico', '.woff', '.woff2'}
THEME_INIT = "try{if(localStorage.getItem('theme')==='dark')document.body.dataset.theme='dark'}catch{}"
THEME_HASH = base64.b64encode(hashlib.sha256(THEME_INIT.encode()).digest()).decode()
POLICY = (
    "default-src 'none'; "
    f"script-src 'self' 'sha256-{THEME_HASH}'; "
    "style-src 'self'; img-src 'self' https:; font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'none'; object-src 'none'; frame-src 'none'; "
    "base-uri 'none'; form-action 'none'"
)


def check_assets(directory: Path) -> None:
    """Fail closed on accidental source/private files, including symlinked trees."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Assets must be a real directory')
    for item in directory.rglob('*'):
        relative = item.relative_to(directory)
        if item.is_symlink():
            raise ValueError(f'Symlink in public assets: {relative}')
        if any(part.startswith('.') for part in relative.parts):
            raise ValueError(f'Hidden entry in public assets: {relative}')
        if item.is_file() and item.suffix.lower() not in ASSET_SUFFIXES:
            raise ValueError(f'Unapproved public asset type: {relative}')
        if not item.is_dir() and not item.is_file():
            raise ValueError(f'Non-regular asset: {relative}')


def harden_page(content: str) -> str:
    metadata = (
        '<meta http-equiv="Content-Security-Policy" content="'+html.escape(POLICY, quote=True)+'">'
        '<meta name="referrer" content="no-referrer">'
    )
    # Place the policy before all resource elements and the theme bootstrap.
    return content.replace('<head>', '<head>'+metadata, 1)


def prepare(output: Path, url: str, as_of: date, *, source: Path = ROOT) -> None:
    safe_url(url)
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.query or parsed.fragment:
        raise ValueError('Pages URL must be https with no query or fragment')
    config = json.loads((source / 'site.json').read_text(encoding='utf-8'))
    config['url'] = f'https://{parsed.netloc}'
    config['base_path'] = parsed.path.rstrip('/')
    renderer = Renderer(config, as_of)
    check_assets(source / 'assets')
    # Keep public output separate from source files.
    if output.is_symlink():
        raise ValueError('Refusing symlink output')
    output = output.resolve()
    source = source.resolve()
    if output == source or output in source.parents or (output.is_relative_to(source) and output != source / 'pages-dist'):
        raise ValueError('Refusing source directory as Pages destination')
    if output.exists() and not (output / '.pages-output').is_file():
        raise ValueError('Refusing to replace an unmarked output directory')
    files = renderer.render()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pages-build-', dir=output.parent) as temporary:
        staging = Path(temporary)
        shutil.copytree(source / 'assets', staging / 'assets')
        for name, content in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(harden_page(content) if name.endswith('.html') else content, encoding='utf-8')
        (staging / '.nojekyll').touch()
        (staging / '.pages-output').write_text('Generated public website; edit the source instead.\n')
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(staging, output)
    print(f'Prepared {len(renderer.posts)} posts for {url} in {output}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Full future Pages URL, including repository path if used')
    parser.add_argument('--output', type=Path, default=ROOT / 'pages-dist')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    prepare(args.output, args.url, args.as_of)


if __name__ == '__main__':
    main()
