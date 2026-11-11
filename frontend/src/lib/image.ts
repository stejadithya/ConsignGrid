/**
 * Shrink a phone photo before upload: longest side ≤ 1280 px, JPEG at medium quality.
 * A 3–5 MB camera photo becomes roughly 100–250 KB, still clear enough to see who and what was delivered.
 */
const MAX_SIDE = 1280;
const TARGET_BYTES = 350 * 1024;

export async function compressPhoto(file: File): Promise<string> {
  const bitmap = await loadImage(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  let quality = 0.65;
  let url = canvas.toDataURL("image/jpeg", quality);
  while (url.length * 0.75 > TARGET_BYTES && quality > 0.35) {
    quality -= 0.1;
    url = canvas.toDataURL("image/jpeg", quality);
  }
  return url;
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const src = URL.createObjectURL(file);
    img.onload = () => { URL.revokeObjectURL(src); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(src); reject(new Error("This file is not a photo")); };
    img.src = src;
  });
}

/** Approximate size of a data URL in KB (for display). */
export const dataUrlKb = (url: string) => Math.round((url.length * 0.75) / 1024);
