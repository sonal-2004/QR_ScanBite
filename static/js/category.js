function filterMenu(category) {

    console.log("CATEGORY CLICKED:", category);

    const products = document.getElementById("products");
    const cards = document.querySelectorAll(".card");

    // Show products section
    products.style.display = "grid";

    let count = 0;

    cards.forEach(function(card) {

        const cardCategory = card.dataset.category;

        if (cardCategory === category) {

            card.hidden = false;
            count++;

        } else {

            card.hidden = true;

        }

    });

    console.log("MATCHING ITEMS:", count);

    // Scroll to food items
    products.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}