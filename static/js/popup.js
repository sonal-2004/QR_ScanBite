let popupName;
let popupPrice;
let popupImage;

let quantity=1;

function openPopup(name, price, image, category){

popupName=name;
popupPrice=price;
popupImage=image;
popupCategory=category;

quantity=1;

document.getElementById("popupName").innerHTML=name;

document.getElementById("popupPrice").innerHTML=price;

document.getElementById("popupImage").src=image;

document.getElementById("qty").innerHTML=quantity;

document.getElementById("cheese").checked=false;
if(category=="Burger"){

        document.getElementById("burgerOptions").style.display="block";
        document.getElementById("pizzaOptions").style.display="none";

    }

    else if(category=="Pizza"){

        document.getElementById("burgerOptions").style.display="none";
        document.getElementById("pizzaOptions").style.display="block";

    }

    else{

        document.getElementById("burgerOptions").style.display="none";
        document.getElementById("pizzaOptions").style.display="none";

    }


document.getElementById("popup").style.display="flex";

}

function closePopup(){

document.getElementById("popup").style.display="none";

}

function increaseQty(){

quantity++;

document.getElementById("qty").innerHTML=quantity;

}

function decreaseQty(){

if(quantity>1){

quantity--;

document.getElementById("qty").innerHTML=quantity;

}

}

function addCustomizedItem(){

let extra = 0;

// Burger cheese
if(document.getElementById("cheese").checked){
    extra += 30;
}

// Pizza cheese
if(document.getElementById("pizzaCheese") &&
   document.getElementById("pizzaCheese").checked){
    extra += 50;
}

// Pizza size
let size=document.querySelector('input[name="size"]:checked');

if(size){
    extra += Number(size.value);
}

addToCart(
    popupName,
    popupPrice + extra,
    popupImage
);

closePopup();

}