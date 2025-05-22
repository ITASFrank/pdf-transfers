function restartGif() {
    const gif = document.getElementById('instructionGif');
    const src = gif.src.split('?')[0]; // Remove any existing query parameters
    gif.src = `${src}?t=${new Date().getTime()}`; // Append a unique timestamp to force reload
}
