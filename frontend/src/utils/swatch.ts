export async function computeImageSwatch(imageUrl: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const size = 24;
      const canvas = document.createElement('canvas');
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d');
      if (!ctx) return reject(new Error('no 2d context'));
      ctx.drawImage(img, 0, 0, size, size);
      let r = 0, g = 0, b = 0, n = 0;
      try {
        const { data } = ctx.getImageData(0, 0, size, size);
        for (let i = 0; i < data.length; i += 4) {
          const a = data[i + 3];
          if (a < 32) continue;
          r += data[i];
          g += data[i + 1];
          b += data[i + 2];
          n++;
        }
      } catch (e) {
        return reject(e);
      }
      if (n === 0) return resolve('#8b8578');
      const toHex = (v: number) => Math.round(v / n).toString(16).padStart(2, '0');
      resolve(`#${toHex(r)}${toHex(g)}${toHex(b)}`);
    };
    img.onerror = () => reject(new Error('image load failed'));
    img.src = imageUrl;
  });
}
