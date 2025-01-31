export async function copyToClipboard(text) {
  if (text) {
    await navigator.clipboard.writeText(text);
  }
}