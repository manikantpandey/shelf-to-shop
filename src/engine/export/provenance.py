"""Mark AI-edited images (India IT Amendment Rules 2026; IPTC Digital Source Type).

A product photo composited onto a generated backdrop is "compositeSynthetic": a composite of
elements, at least one of which is synthetic (https://cv.iptc.org/newscodes/digitalsourcetype/).
C2PA content credentials are a documented follow-up: signing needs a certificate from a CA on the
C2PA trust list.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from PIL import Image

COMPOSITE_SYNTHETIC = "http://cv.iptc.org/newscodes/digitalsourcetype/compositeSynthetic"
PHOTO_ORIGINAL = "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture"


def xmp_packet(source_type: str, description: str, tool: str = "Shelf-to-Shop") -> bytes:
    desc = escape(description)
    packet = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    Iptc4xmpExt:DigitalSourceType="{escape(source_type)}"
    xmp:CreatorTool="{escape(tool)}">
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{desc}</rdf:li></rdf:Alt></dc:description>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    return packet.encode("utf-8")


def save_jpeg(image: Image.Image, *, ai_background: bool, quality: int = 88) -> bytes:
    """JPEG with XMP provenance and no other metadata (no EXIF, no location)."""
    if ai_background:
        xmp = xmp_packet(
            COMPOSITE_SYNTHETIC,
            "Product photo. Background generated with AI (Muse Image); product pixels unedited.",
        )
    else:
        xmp = xmp_packet(PHOTO_ORIGINAL, "Product photo with a plain background.")
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, xmp=xmp)
    return buf.getvalue()
