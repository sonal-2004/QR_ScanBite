let quantity = 1;

function increase(){

quantity++;

document.getElementById("qty").innerHTML=quantity;

}

function decrease(){

if(quantity>1){

quantity--;

document.getElementById("qty").innerHTML=quantity;

}

}

function addCombo(){

addToCart(

"Burger Combo",

399*quantity,

"/static/images/burger-fries.jpeg"

);

window.location.href="/cart";

}