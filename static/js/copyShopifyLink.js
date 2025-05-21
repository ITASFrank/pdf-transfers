function copyShopifyLink() {
    navigator.clipboard.writeText("2a7006-21.myshopify.com").then(() => {
        const popup = document.createElement("div");
        popup.textContent = "Copied!";
        popup.style.position = "fixed";
        popup.style.bottom = "20px";
        popup.style.right = "20px";
        popup.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
        popup.style.color = "#fff";
        popup.style.padding = "10px 20px";
        popup.style.borderRadius = "5px";
        popup.style.fontSize = "1em";
        popup.style.zIndex = "1051";
        popup.style.opacity = "0";
        popup.style.transition = "opacity 0.3s ease";

        document.body.appendChild(popup);

        // Fade in the popup
        setTimeout(() => {
            popup.style.opacity = "1";
        }, 10);

        // Remove the popup after 2 seconds
        setTimeout(() => {
            popup.style.opacity = "0";
            setTimeout(() => popup.remove(), 300);
        }, 2000);
    });
}
