const swiper = new Swiper(".mySwiper", {
  spaceBetween: 30,
  centeredSlides: true,
  autoplay: {
    delay: 3500,
    disableOnInteraction: false,
  },
  pagination: {
    el: ".swiper-pagination",
    clickable: true,
  },
});

// Khởi tạo Isotope
const elem = document.querySelector(".product-wrapper");
const iso = new Isotope(elem, {
  itemSelector: ".product-card",
  layoutMode: "fitRows",
});

// Sự kiện lọc sản phẩm
const filtersElem = document.querySelector("#filter");
filtersElem.addEventListener("click", function (event) {
  if (!event.target.matches("button")) return;
  const filterValue = event.target.getAttribute("data-filter");
  iso.arrange({ filter: filterValue });
});

// Xử lý nhóm nút lọc
const buttonGroups = document.querySelectorAll(".filter-group");
for (let i = 0; i < buttonGroups.length; i++) {
  const buttonGroup = buttonGroups[i];
  radioButtonGroup(buttonGroup);
}

// Chỉ một nút "is-checked" trong mỗi nhóm
function radioButtonGroup(buttonGroup) {
  buttonGroup.addEventListener("click", function (event) {
    if (!event.target.matches("button")) return;
    const current = buttonGroup.querySelector(".is-checked");
    if (current) current.classList.remove("is-checked");
    event.target.classList.add("is-checked");
  });
}

// =================== Giỏ hàng (Cart System) ===================

// Lưu giỏ hàng vào localStorage
function saveCart(cart) {
  localStorage.setItem("cart", JSON.stringify(cart));
}

// Lấy giỏ hàng từ localStorage
function getCart() {
  return JSON.parse(localStorage.getItem("cart")) || [];
}

// Thêm sản phẩm vào giỏ hàng
function addToCart(product) {
  let cart = getCart();
  const existing = cart.find((item) => item.name === product.name);
  if (existing) {
    existing.quantity += 1;
  } else {
    cart.push(product);
  }
  saveCart(cart);
  alert("🛒 Đã thêm sản phẩm vào giỏ hàng!");
}

// Xóa sản phẩm khỏi giỏ hàng
function removeFromCart(name) {
  let cart = getCart().filter((item) => item.name !== name);
  saveCart(cart);
}

// Hiển thị giỏ hàng trong cart.html
function renderCart() {
  const cartWrapper = document.getElementById("cart-items");
  const totalEl = document.getElementById("cart-total");
  if (!cartWrapper || !totalEl) return; // Nếu không phải trang giỏ hàng thì thoát

  const cart = getCart();
  cartWrapper.innerHTML = "";

  let total = 0;

  cart.forEach((item) => {
    total += item.price * item.quantity;
    const card = document.createElement("div");
    card.classList.add("product-card");
    card.innerHTML = `
      <img src="${item.image}" class="product-image" alt="${item.name}" />
      <div class="product-detail">
        <h3>${item.name}</h3>
        <span>$${item.price}</span>
        <p>Quantity: 
          <input type="number" value="${item.quantity}" min="1" class="qty-input" />
        </p>
        <button class="product-button remove-btn">Remove</button>
      </div>
    `;
    cartWrapper.appendChild(card);

    // Xử lý thay đổi số lượng
    const qtyInput = card.querySelector(".qty-input");
    qtyInput.addEventListener("change", () => {
      item.quantity = parseInt(qtyInput.value);
      saveCart(cart);
      renderCart();
    });

    // Xử lý xóa sản phẩm
    card.querySelector(".remove-btn").addEventListener("click", () => {
      removeFromCart(item.name);
      renderCart();
    });
  });

  totalEl.textContent = `$${total}`;
}

// Khi click nút “Add to Cart” trong index.html
document.addEventListener("click", function (e) {
  if (e.target.classList.contains("product-button")) {
    const card = e.target.closest(".product-card");
    if (!card) return;
    const name = card.querySelector("h3").textContent;
    const price = parseFloat(
      card.querySelector("span").textContent.replace("$", "")
    );
    const image = card.querySelector(".product-image").getAttribute("src");

    addToCart({ name, price, image, quantity: 1 });
  }
});

// Khi vào trang giỏ hàng thì render lại sản phẩm
window.addEventListener("DOMContentLoaded", renderCart);

const searchInput = document.getElementById("searchInput");
searchInput.addEventListener("input", function () {
  const keyword = this.value.toLowerCase();
  iso.arrange({
    filter: (itemElem) => {
      const name = itemElem.querySelector("h3").textContent.toLowerCase();
      return name.includes(keyword);
    },
  });
});

// ===================== Xử lý đăng xuất =====================
document.addEventListener("DOMContentLoaded", () => {
  const logoutLink = document.getElementById("logout-link");
  if (logoutLink) {
    logoutLink.addEventListener("click", (e) => {
      e.preventDefault();
      // Có thể thêm xác nhận
      alert("Bạn đã đăng xuất!");
      window.location.href = "/login"; // hoặc "login.html" nếu là tĩnh
    });
  }
});
