// let cart = JSON.parse(localStorage.getItem("cart")) || [];

// function addToCart(name, price, image){

//     let item = cart.find(x => x.name === name);

//     if(item){

//         item.qty++;

//     }

//     else{

//         cart.push({

//             name:name,
//             price:Number(price),
//             image:image,
//             qty:1

//         });

//     }

//     localStorage.setItem("cart",JSON.stringify(cart));

//     updateCartBadge();

// }

// function updateCartBadge(){

//     cart = JSON.parse(localStorage.getItem("cart")) || [];

//     let count = 0;

//     let total = 0;

//     cart.forEach(item=>{

//         count += item.qty;

//         total += item.price * item.qty;

//     });

//     let countElement=document.getElementById("cart-count");

//     let totalElement=document.getElementById("cart-total");

//     let floating=document.getElementById("floating-cart");

//     if(countElement) countElement.innerHTML=count;

//     if(totalElement) totalElement.innerHTML=total;

//     if(floating){

//         floating.style.display = count>0 ? "flex" : "none";

//     }

// }

// window.onload=function(){

//     updateCartBadge();

// }

// function openCart(){

//     window.location="/cart";

// }
// =====================================================
// SCANBITE CART SYSTEM
// =====================================================

// Load cart from sessionStorage
// sessionStorage is cleared when the browser session/tab ends
// =====================================================
// SCANBITE CART
// =====================================================

let cart = JSON.parse(sessionStorage.getItem("cart")) || [];

const CART_EXPIRY = 3 * 60 * 1000; // 3 minutes


// =====================================================
// CHECK CART EXPIRY
// =====================================================

function checkCartExpiry() {

    const cartTime = sessionStorage.getItem("cartTime");

    if (!cartTime) {
        return;
    }

    const difference = Date.now() - Number(cartTime);

    if (difference >= CART_EXPIRY) {

        sessionStorage.removeItem("cart");
        sessionStorage.removeItem("cartTime");

        cart = [];

        updateCartBadge();
    }
}


// =====================================================
// ADD TO CART
// =====================================================

function addToCart(name, price, image) {

    checkCartExpiry();

    let item = cart.find(x => x.name === name);

    if (item) {

        item.qty++;

    } else {

        cart.push({

            name: name,
            price: Number(price),
            image: image,
            qty: 1

        });

    }

    sessionStorage.setItem(
        "cart",
        JSON.stringify(cart)
    );

    sessionStorage.setItem(
        "cartTime",
        Date.now()
    );

    updateCartBadge();
}


// =====================================================
// UPDATE CART BADGE
// =====================================================

function updateCartBadge() {

    checkCartExpiry();

    cart =
        JSON.parse(
            sessionStorage.getItem("cart")
        ) || [];

    let count = 0;
    let total = 0;

    cart.forEach(item => {

        count += Number(item.qty);

        total +=
            Number(item.price) *
            Number(item.qty);

    });


    const countElement =
        document.getElementById("cart-count");

    const totalElement =
        document.getElementById("cart-total");

    const floating =
        document.getElementById("floating-cart");


    if (countElement) {

        countElement.innerHTML = count;

    }


    if (totalElement) {

        totalElement.innerHTML = total;

    }


    if (floating) {

        floating.style.display =
            count > 0 ? "flex" : "none";

    }

}


// =====================================================
// OPEN CART
// =====================================================

function openCart() {

    checkCartExpiry();

    window.location.href = "/cart";

}


// =====================================================
// CLEAR CART
// =====================================================

function clearCartData() {

    sessionStorage.removeItem("cart");

    sessionStorage.removeItem("cartTime");

    cart = [];

    updateCartBadge();

}


// =====================================================
// PAGE LOAD
// =====================================================

window.addEventListener("load", function () {

    checkCartExpiry();

    updateCartBadge();

});


// =====================================================
// CHECK EVERY 10 SECONDS
// =====================================================

setInterval(function () {

    checkCartExpiry();

}, 10000);