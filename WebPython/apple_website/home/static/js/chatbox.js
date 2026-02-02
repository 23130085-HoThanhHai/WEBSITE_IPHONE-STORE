document.addEventListener('DOMContentLoaded', function() {
    const toggleBtn = document.getElementById('chat-toggle');
    const chatContainer = document.getElementById('chat-container');
    const sendBtn = document.getElementById('send-btn');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    toggleBtn.addEventListener('click', () => {
        chatContainer.style.display =
            chatContainer.style.display === 'none' ? 'flex' : 'none';
    });

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // Tin nhắn user
        chatMessages.innerHTML += `
          <div style="background:#007bff;color:white;padding:8px 12px;
          border-radius:15px;align-self:flex-end;">
            ${text}
          </div>`;
        chatInput.value = '';
        chatMessages.scrollTop = chatMessages.scrollHeight;

        const loadingId = 'loading-' + Date.now();
        chatMessages.innerHTML += `
          <div id="${loadingId}" style="color:#888;font-style:italic;font-size:12px;">
            Đang tìm kiếm sản phẩm...
          </div>`;

        try {
            const response = await fetch('/chat/api/', {   // ✅ SỬA Ở ĐÂY
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ message: text })   // ✅ SỬA Ở ĐÂY
            });

            const data = await response.json();
            document.getElementById(loadingId).remove();

            // Tin nhắn bot
            chatMessages.innerHTML += `
              <div style="background:#f1f1f1;padding:8px 12px;
              border-radius:15px;align-self:flex-start;">
                ${data.reply}
              </div>`;
            chatMessages.scrollTop = chatMessages.scrollHeight;

        } catch (error) {
            document.getElementById(loadingId).innerText =
                "❌ Lỗi kết nối hệ thống.";
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
