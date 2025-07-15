// static/app.js (Tam ve Son Hali)

document.addEventListener('DOMContentLoaded', () => {
    // --- Elementleri Seçme ---
    const logArea = document.getElementById('log-area');
    const positionInfo = document.getElementById('position-info');
    const statusIndicator = document.getElementById('status-indicator');
    
    // Butonlar
    const startBotBtn = document.getElementById('start-bot');
    const stopBotBtn = document.getElementById('stop-bot');
    const manualLongBtn = document.getElementById('manual-long');
    const manualShortBtn = document.getElementById('manual-short');
    const setLeverageBtn = document.getElementById('set-leverage');
    const setQuantityBtn = document.getElementById('set-quantity');
    const emergencyCloseBtn = document.getElementById('emergency-close');
    
    // Girdiler
    const leverageInput = document.getElementById('leverage');
    const quantityInput = document.getElementById('quantity');
    const historyBody = document.getElementById('history-body');

    // --- Yardımcı Fonksiyonlar ---
    function addLog(message) {
        const timestamp = new Date().toLocaleTimeString('tr-TR');
        logArea.innerHTML += `[${timestamp}] ${message}\n`;
        logArea.scrollTop = logArea.scrollHeight;
    }

    function updatePositionInfo(data) {
        if (!data || parseFloat(data.quantity) === 0) {
            positionInfo.innerHTML = '<p>Açık pozisyon yok.</p>';
            return;
        }
        const pnlColor = parseFloat(data.pnl_usdt) >= 0 ? 'success' : 'danger';
        positionInfo.innerHTML = `
            <p><strong>Sembol:</strong> ${data.symbol}</p>
            <p><strong>Büyüklük:</strong> ${data.quantity}</p>
            <p><strong>Giriş Fiyatı:</strong> ${data.entry_price}</p>
            <p><strong>PNL (USDT):</strong> <span class="pnl-${pnlColor}">${data.pnl_usdt}</span></p>
            <p><strong>ROI:</strong> <span class="pnl-${pnlColor}">${data.roi_percent}</span></p>
        `;
    }

    // API'ye istek göndermek için genel bir fonksiyon
    async function postData(url, data = {}) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.message) {
                addLog(`Sunucu Yanıtı: ${result.message}`);
            }
        } catch (error) {
            addLog(`API Hatası: ${error}`);
            console.error('API isteği başarısız:', error);
        }
    }
    
    // --- WebSocket Bağlantısı ---
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        statusIndicator.className = 'status-online';
        addLog('Sunucuya bağlanıldı.');
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        switch (message.type) {
            case 'log':
                addLog(message.data);
                break;
            case 'position_update':
                updatePositionInfo(message.data);
                break;
            case 'history_update':
                // TODO: Geçmişi yenileme fonksiyonu eklenebilir
                break;
        }
    };

    ws.onclose = () => {
        statusIndicator.className = 'status-offline';
        addLog('Sunucu bağlantısı koptu. Sayfa yenilenebilir.');
    };

    ws.onerror = (error) => {
        addLog('WebSocket hatası oluştu.');
        console.error('WebSocket Error:', error);
    };

    // --- Butonlara İşlev Atama (Event Listeners) ---
    startBotBtn.addEventListener('click', () => {
        addLog("'Başlat' butonuna tıklandı. Sunucuya komut gönderiliyor...");
        postData('/start');
    });

    stopBotBtn.addEventListener('click', () => {
        addLog("'Durdur' butonuna tıklandı. Sunucuya komut gönderiliyor...");
        postData('/stop');
    });

    manualLongBtn.addEventListener('click', () => {
        addLog("'Market LONG' butonuna tıklandı. Sunucuya komut gönderiliyor...");
        postData('/manual-trade/long');
    });

    manualShortBtn.addEventListener('click', () => {
        addLog("'Market SHORT' butonuna tıklandı. Sunucuya komut gönderiliyor...");
        postData('/manual-trade/short');
    });

    emergencyCloseBtn.addEventListener('click', () => {
        if (confirm('Açık pozisyon piyasa emriyle kapatılacak. Emin misiniz?')) {
            addLog("'Pozisyonu Kapat' butonuna tıklandı. Sunucuya komut gönderiliyor...");
            postData('/emergency-close');
        }
    });

    setLeverageBtn.addEventListener('click', () => {
        const leverage = parseInt(leverageInput.value);
        if (leverage > 0) {
            addLog(`Kaldıraç ${leverage}x olarak ayarlanıyor...`);
            postData('/set-leverage', { leverage: leverage });
        } else {
            addLog("Geçersiz kaldıraç değeri.");
        }
    });

    setQuantityBtn.addEventListener('click', () => {
        const quantity_usd = parseFloat(quantityInput.value);
        if (quantity_usd >= 5) {
            addLog(`İşlem miktarı ~${quantity_usd} USDT olarak ayarlanıyor...`);
            postData('/set-quantity', { quantity_usd: quantity_usd });
        } else {
            addLog("İşlem miktarı en az 5 USDT olmalıdır.");
        }
    });
});
