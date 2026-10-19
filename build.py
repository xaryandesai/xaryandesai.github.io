"""Build the personal website using only the Python standard library."""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
escape = html.escape
RESERVED = {'blog', 'assets', 'tags', 'teaching', '404', 'feed', 'index', 'sitemap', 'robots'}
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
SUN = '<svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>'
MOON = '<svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 14.1A8.7 8.7 0 0 1 9.9 3.5 8.8 8.8 0 1 0 20.5 14.1Z"/></svg>'
ICONS = {
    'x': '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" stroke="none" d="M18.9 1.2h3.7l-8 9.2L24 22.8h-7.4l-5.8-7.6-6.6 7.6H.5l8.6-9.8L0 1.2h7.6l5.2 6.9ZM17.6 20.6h2L6.5 3.2H4.3Z"/></svg>',
    'linkedin': '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" stroke="none" d="M2 0h20a2 2 0 0 1 2 2v20a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2ZM4 9h3.5v11H4Zm1.75-5.5a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 0 0 0-3.8ZM10 9h3.4v1.5c.7-1.1 1.8-1.8 3.4-1.8 3.1 0 4.2 2 4.2 5V20h-3.5v-5.7c0-1.6-.4-2.6-1.9-2.6s-2.2 1.1-2.2 2.6V20H10Z"/></svg>',
    'email': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 6 10 7 10-7"/></svg>',
}


def display_date(value: str, padded: bool = True) -> str:
    d = date.fromisoformat(value)
    day = f'{d.day:02d}' if padded else str(d.day)
    return f'{MONTHS[d.month - 1]} {day}, {d.year}'


def safe_url(value: str, *, local: bool = False) -> str:
    """Allow web URLs, and optionally root-relative authored asset paths."""
    if any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError(f'Invalid URL: {value!r}')
    parsed = urlsplit(value)
    if local and value.startswith('/') and not value.startswith('//'):
        if '..' not in parsed.path.split('/'):
            return value
    if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password:
        return value
    raise ValueError(f'Expected an http(s) URL{" or root-relative path" if local else ""}: {value!r}')


def validate(config: dict[str, Any]) -> None:
    if not isinstance(config.get('name'), str) or not config['name'].strip():
        raise ValueError('name must be a nonempty string')
    for key in ('bio', 'photo', 'url', 'base_path'):
        if key in config and not isinstance(config[key], str):
            raise ValueError(f'{key} must be a string')
    if config.get('url'):
        safe_url(config['url'])
        parsed = urlsplit(config['url'])
        if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('url must be an origin; use base_path for a subdirectory')
    base = config.get('base_path', '')
    if base and not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+', base):
        raise ValueError('base_path must be empty or a path such as /my-site')
    if config.get('photo'):
        safe_url(config['photo'], local=True)
    social = config.get('social', {})
    if not isinstance(social, dict):
        raise ValueError('social must be an object')
    for kind in ('x', 'linkedin', 'email'):
        value = social.get(kind, '')
        if not isinstance(value, str):
            raise ValueError(f'social.{kind} must be a string')
        if value and kind != 'email':
            safe_url(value)
        elif value and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
            raise ValueError('Invalid email address')
    if not isinstance(config.get('posts'), list):
        raise ValueError('posts must be a list')
    seen = set()
    for post in config['posts']:
        if not isinstance(post, dict):
            raise ValueError('Each post must be an object')
        slug = post.get('slug', '')
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug in RESERVED or slug in seen:
            raise ValueError(f'Invalid, reserved or duplicate post slug: {slug!r}')
        seen.add(slug)
        for key in ('title', 'date'):
            if not isinstance(post.get(key), str) or not post[key].strip():
                raise ValueError(f'{slug}: {key} must be a nonempty string')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', post['date']):
            raise ValueError(f'{slug}: date must use YYYY-MM-DD')
        date.fromisoformat(post['date'])
        if 'updated' in post:
            date.fromisoformat(post['updated'])
            if post['updated'] < post['date']:
                raise ValueError('updated cannot precede date')
        if 'draft' in post and not isinstance(post['draft'], bool):
            raise ValueError('draft must be true or false')
        for key in ('excerpt', 'body_html', 'thumbnail', 'image', 'image_alt'):
            if key in post and not isinstance(post[key], str):
                raise ValueError(f'{slug}: {key} must be a string')
        for key in ('thumbnail', 'image'):
            if post.get(key):
                safe_url(post[key], local=True)
        if post.get('image') and not post.get('image_alt', '').strip():
            raise ValueError('Article image requires image_alt')
        if 'tags' in post and (not isinstance(post['tags'], list) or any(not isinstance(t, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', t) for t in post['tags'])):
            raise ValueError('tags must be a list of lowercase slugs')


def anchor_headings(body: str) -> str:
    """Add shareable permalinks to authored headings without copying reference code."""
    used = set(re.findall(r'\bid=[\"\']([^\"\']+)', body))

    def replace(match: re.Match[str]) -> str:
        level, attrs, text = match.groups()
        existing = re.search(r'\bid=[\"\']([^\"\']+)', attrs)
        if existing:
            anchor = existing.group(1)
        else:
            plain = html.unescape(re.sub(r'<[^>]+>', '', text))
            stem = re.sub(r'[^\w-]+', '-', plain.lower()).strip('-') or 'section'
            anchor, suffix = stem, 2
            while anchor in used or anchor == 'content':
                anchor = f'{stem}-{suffix}'
                suffix += 1
            used.add(anchor)
            attrs += f' id="{escape(anchor)}"'
        label = escape(html.unescape(re.sub(r'<[^>]+>', '', text)))
        return f'<h{level}{attrs}><a class="anchor-head" href="#{escape(anchor)}" aria-label="Link to {label}">#</a>{text}</h{level}>'

    return re.sub(r'<h([1-4])([^>]*)>(.*?)</h\1>', replace, body, flags=re.DOTALL | re.IGNORECASE)


class Renderer:
    def __init__(self, config: dict[str, Any], as_of: date):
        validate(config)
        self.config = config
        self.as_of = as_of
        self.posts = sorted((p for p in config['posts'] if not p.get('draft', False) and date.fromisoformat(p['date']) <= as_of), key=lambda p: (p['date'], p['slug']), reverse=True)

    def path(self, path: str) -> str:
        return self.config.get('base_path', '') + path

    def absolute(self, path: str) -> str:
        return self.config.get('url', '').rstrip('/') + self.path(path)

    def asset(self, url: str) -> str:
        return self.path(url) if url.startswith('/') else url

    def social(self) -> str:
        result = []
        for kind, label in [('x', 'X'), ('linkedin', 'LinkedIn'), ('email', 'Email')]:
            value = self.config.get('social', {}).get(kind, '')
            if not value:
                result.append(f'<button type="button" disabled aria-label="{label} not configured" title="{label} not configured">{ICONS[kind]}</button>')
            elif kind == 'email':
                envelope = ICONS[kind].replace('<svg ', '<svg class="email-envelope" ', 1)
                check = '<svg class="email-check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
                result.append(f'<button class="copy-email" type="button" data-email="{escape(value)}" aria-label="Copy email address">{envelope}{check}</button>')
            else:
                result.append(f'<a href="{escape(value)}" target="_blank" rel="noopener noreferrer" aria-label="{label}">{ICONS[kind]}</a>')
        return '<div class="author-links">' + ''.join(result) + '</div><span class="sr-only" id="copy-status" role="status" aria-live="polite"></span>'

    def page(self, active: str, content: str, *, profile: bool = False, post: dict[str, Any] | None = None, title: str = '', route: str = '/') -> str:
        name = escape(self.config['name'])
        title = post['title'] if post else title
        document_title = f'{title} - {self.config["name"]}' if title else self.config['name']
        description = post.get('excerpt', '') if post else (self.config.get('bio') or f'{self.config["name"]}\'s personal website')
        metadata = f'<meta name="description" content="{escape(description)}"><meta property="og:title" content="{escape(document_title)}"><meta property="og:description" content="{escape(description)}"><meta property="og:type" content="{"article" if post else "website"}"><meta name="twitter:card" content="summary">'
        if self.config.get('url'):
            metadata += f'<link rel="canonical" href="{escape(self.absolute(route))}"><meta property="og:url" content="{escape(self.absolute(route))}">'
        if post:
            metadata += f'<meta property="article:published_time" content="{post["date"]}T00:00:00Z">'
            image = post.get('image') or post.get('thumbnail')
            if image:
                absolute_image = self.absolute(image) if image.startswith('/') else image
                metadata += f'<meta property="og:image" content="{escape(absolute_image)}">'
        nav = ''.join(f'<a class="menu-link {"active" if key == active else ""}" href="{self.path(url)}"'+(' aria-current="page"' if key == active else '')+f'>{label}</a>' for key, label, url in [('home', 'Home', '/'), ('blog', 'Blog', '/blog/')])
        author = ''
        if profile:
            photo = self.asset(self.config.get('photo') or '/assets/img/avatar-placeholder.svg')
            alt = f'{self.config["name"]} profile photo' if self.config.get('photo') else 'Profile photo placeholder'
            bio = escape(self.config.get('bio') or 'Your short introduction goes here.')
            author = f'<div class="author"><img class="author-avatar" src="{escape(photo)}" alt="{escape(alt)}" width="70" height="70"><h2 class="author-name">{name}</h2><p class="author-bio">{bio}</p>{self.social()}</div>'
        return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(document_title)}</title>{metadata}
<link rel="icon" type="image/svg+xml" href="{self.path('/assets/img/favicon.svg')}">
<link rel="stylesheet" href="{self.path('/assets/css/style.css')}"><link rel="stylesheet" href="{self.path('/assets/css/template.css')}">
<link rel="alternate" type="application/atom+xml" href="{self.path('/feed.xml')}" title="{name}"></head>
<body class="notransition"><script>try{{if(localStorage.getItem('theme')==='dark')document.body.dataset.theme='dark'}}catch{{}}</script>
<a href="#content" class="skip-link">Skip to content</a>
<div class="navbar"><nav class="menu" aria-label="Main navigation">
<button id="menu-toggle" type="button" aria-label="Open navigation" aria-expanded="false" aria-controls="navigation-links"><svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18v2H3zm0 6h18v2H3zm0 6h18v2H3z"/></svg></button>
<button id="mode" type="button" aria-label="Switch to dark theme" aria-pressed="false">{SUN}{MOON}</button>
<div class="trigger" id="navigation-links"><div class="trigger-container">{nav}</div></div></nav></div>
<div class="wrapper{' post' if post else ''}">{author}<main id="content" tabindex="-1" class="{'' if profile else 'page-content'}" aria-label="Content">{content}</main>
<footer class="footer"><small class="footer_copyright">© {name}</small></footer></div>
<script src="{self.path('/assets/js/main.js')}" defer></script></body></html>'''

    def render(self) -> dict[str, str]:
        files = {}
        home_rows, blog_rows = [], []
        last_year = ''
        for post in self.posts:
            route = f'/{post["slug"]}/'
            url, title = escape(self.path(route)), escape(post['title'])
            d = post['date']
            home_rows.append(f'<article class="post-item"><time class="post-item-date" datetime="{d}">{display_date(d)}</time><h4 class="post-item-title"><a href="{url}">{title}</a></h4></article>')
            if d[:4] != last_year:
                blog_rows.append(f'<h2>{d[:4]}</h2>')
                last_year = d[:4]
            thumbnail = f'<img src="{escape(self.asset(post["thumbnail"]))}" alt="" loading="lazy" width="168" height="95">' if post.get('thumbnail') else ''
            blog_rows.append(f'<article class="blog-entry"><a class="blog-card" href="{url}"><span class="blog-thumbnail" aria-hidden="true">{thumbnail}</span><div class="blog-card-copy"><time class="blog-date" datetime="{d}">{display_date(d, False)}</time><h3>{title}</h3><p>{escape(post.get("excerpt", ""))}</p><span class="blog-action">Read article →</span></div></a></article>')
            tags = ', '.join(f'<a class="tag" href="{self.path("/tags/")}#{tag}">{escape(tag.upper())}</a>' for tag in post.get('tags', []))
            tag_row = f'<div class="tags">{tags}</div>' if tags else ''
            image = ''
            if post.get('image'):
                src = escape(self.asset(post['image']))
                image = f'<figure class="post-hero"><a href="{src}" aria-label="View full photo: {escape(post["image_alt"])}"><img src="{src}" alt="{escape(post["image_alt"])}"></a></figure>'
            body = anchor_headings(post.get('body_html', ''))
            # Root-relative authored content URLs use the optional deployment base path.
            if self.config.get('base_path'):
                body = re.sub(r'(\b(?:href|src)=)([\"\'])(/(?!/)[^\"\']*)\2', lambda m: m[1]+m[2]+self.path(m[3])+m[2], body)
            article = f'<article itemscope itemtype="https://schema.org/BlogPosting"><header class="header">{tag_row}<h1 class="header-title" itemprop="headline">{title}</h1><div class="post-meta"><time datetime="{d}" itemprop="datePublished">{display_date(d)}</time><span itemprop="author">{escape(self.config["name"])}</span></div></header><div class="page-content article-body" itemprop="articleBody">{image}{body}<p class="back-to-blog"><a href="{self.path("/blog/")}">← Back to the blog</a></p></div></article>'
            files[f'{post["slug"]}/index.html'] = self.page('blog', article, post=post, route=route)
        files['index.html'] = self.page('home', '<h3 class="posts-item-note">Recent Posts</h3>'+''.join(home_rows[:5]), profile=True)
        files['blog/index.html'] = self.page('blog', ''.join(blog_rows) or '<h1>Blog</h1>', title='Blog', route='/blog/')
        all_tags = sorted({tag for post in self.posts for tag in post.get('tags', [])})
        if all_tags:
            rows = []
            for tag in all_tags:
                rows.append(f'<h2 id="{tag}">{escape(tag)}</h2>')
                rows.extend(f'<p><a href="{self.path("/"+p["slug"]+"/")}">{escape(p["title"])}</a></p>' for p in self.posts if tag in p.get('tags', []))
            files['tags/index.html'] = self.page('blog', ''.join(rows), title='Tags', route='/tags/')
        files['404.html'] = self.page('', f'<div class="not-found"><h1 class="title">404</h1><p>Page not found.</p><a href="{self.path("/")}">Back to Home</a></div>', title='Page not found', route='/404.html')
        files['feed.xml'] = self.feed()
        if self.config.get('url'):
            ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
            ET.register_namespace('', ns)
            sitemap = ET.Element(f'{{{ns}}}urlset')
            for route in ['/', '/blog/'] + [f'/{p["slug"]}/' for p in self.posts] + (['/tags/'] if all_tags else []):
                child = ET.SubElement(sitemap, f'{{{ns}}}url')
                ET.SubElement(child, f'{{{ns}}}loc').text = self.absolute(route)
            files['sitemap.xml'] = ET.tostring(sitemap, encoding='unicode', xml_declaration=True)
        return files

    def feed(self) -> str:
        ns = 'http://www.w3.org/2005/Atom'
        ET.register_namespace('', ns)
        root = ET.Element(f'{{{ns}}}feed')

        def add(parent: ET.Element, key: str, text: str = '', **attrs: str) -> ET.Element:
            child = ET.SubElement(parent, f'{{{ns}}}{key}', attrs)
            child.text = text or None
            return child

        origin = self.config.get('url')
        add(root, 'title', self.config['name'])
        add(root, 'id', self.absolute('/') if origin else 'urn:aryan-desai:feed')
        updated = max((p.get('updated', p['date']) for p in self.posts), default='2026-10-14')
        add(root, 'updated', updated+'T00:00:00Z')
        add(add(root, 'author'), 'name', self.config['name'])
        if origin:
            add(root, 'link', href=self.absolute('/feed.xml'), rel='self')
            add(root, 'link', href=self.absolute('/'))
        for post in self.posts:
            entry = add(root, 'entry')
            url = self.absolute(f'/{post["slug"]}/') if origin else 'urn:aryan-desai:post:'+post['slug']
            add(entry, 'id', url)
            add(entry, 'title', post['title'])
            add(entry, 'published', post['date']+'T00:00:00Z')
            add(entry, 'updated', post.get('updated', post['date'])+'T00:00:00Z')
            add(entry, 'summary', post.get('excerpt', ''))
            if origin:
                add(entry, 'link', href=url)
        return ET.tostring(root, encoding='unicode', xml_declaration=True)


def build(config_path: Path, output: Path, as_of: date) -> None:
    config = json.loads(config_path.read_text(encoding='utf-8'))
    renderer = Renderer(config, as_of)
    files = renderer.render()
    if output.is_symlink():
        raise ValueError('Refusing symlink output directory')
    output = output.resolve()
    if output == ROOT or output in ROOT.parents or output == ROOT / 'assets' or output.is_symlink():
        raise ValueError('Refusing unsafe output directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Validate/render first; stage before replacing known generated output.
    with tempfile.TemporaryDirectory(prefix='.site-build-', dir=output.parent) as temp:
        staging = Path(temp)
        shutil.copytree(ROOT / 'assets', staging / 'assets')
        for path, content in files.items():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        if output.exists():
            if not (output / '.generated-site').is_file() and output != ROOT / 'dist':
                raise ValueError('Refusing to replace an unmarked output directory')
            shutil.rmtree(output)
        (staging / '.generated-site').write_text('Generated by build.py. Edit assets/ and site.json.\n')
        shutil.copytree(staging, output)
    print(f'Rendered {len(renderer.posts)} published posts into {output}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'site.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    build(args.config, args.output, args.as_of)


if __name__ == '__main__':
    main()
