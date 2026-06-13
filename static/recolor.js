// Shared penguin recolor utilities — included on home.html, character_creation.html, profile.html
const _recolorCache = {};

function recolorPenguin(sourceImage, targetColor) {
    const offscreen = document.createElement('canvas');
    offscreen.width  = sourceImage.width  || sourceImage.naturalWidth  || 64;
    offscreen.height = sourceImage.height || sourceImage.naturalHeight || 40;
    const ctx = offscreen.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(sourceImage, 0, 0);
    const imageData = ctx.getImageData(0, 0, offscreen.width, offscreen.height);
    const pixels    = imageData.data;
    const tr = parseInt(targetColor.slice(1,3), 16);
    const tg = parseInt(targetColor.slice(3,5), 16);
    const tb = parseInt(targetColor.slice(5,7), 16);
    for (let i = 0; i < pixels.length; i += 4) {
        const r = pixels[i], g = pixels[i+1], b = pixels[i+2], a = pixels[i+3];
        if (a === 0) continue;
        const brightness = (r + g + b) / 3;
        if (brightness > 180) continue;          // belly / white areas
        if (r > 150 && g > 80 && g < 180 && b < 80) continue; // beak / feet (orange)
        if (brightness < 15) continue;           // hard outline — keep black
        const scale = brightness / 100;
        pixels[i]   = Math.min(255, Math.floor(tr * scale));
        pixels[i+1] = Math.min(255, Math.floor(tg * scale));
        pixels[i+2] = Math.min(255, Math.floor(tb * scale));
    }
    ctx.putImageData(imageData, 0, 0);
    return offscreen;
}

function getRecoloredSprite(spriteKey, sourceImage, color) {
    const key = `${spriteKey}_${color}`;
    if (_recolorCache[key]) return _recolorCache[key];
    const result = recolorPenguin(sourceImage, color);
    _recolorCache[key] = result;
    return result;
}
