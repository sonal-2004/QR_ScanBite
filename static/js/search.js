function searchMenu() {

    let input = document.getElementById("search").value.toLowerCase();

    let products = document.getElementById("products");

    let slider = document.getElementById("slider");

    let categories = document.getElementById("categories");

    let specials = document.getElementById("specials");

    if(input===""){

        slider.style.display="block";
        categories.style.display="grid";
        specials.style.display="block";
        products.style.display="none";

        return;
    }

    slider.style.display="none";
    categories.style.display="none";
    specials.style.display="none";
    products.style.display="grid";

    let cards=document.querySelectorAll(".card");

    cards.forEach(card=>{

        let name=card.querySelector("h4").innerText.toLowerCase();

        if(name.includes(input)){

            card.style.display="block";

        }else{

            card.style.display="none";

        }

    });

}