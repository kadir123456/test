document.addEventListener('DOMContentLoaded', () => {
    const logArea = document.getElementById('log-area');
    const positionInfo = document.getElementById('position-info');
    const statusIndicator = document.getElementById('status-indicator');

    function addLog(message) {
        const timestamp = new Date().toLocaleTimeString();
        logArea.innerHTML += `[${timestamp}] ${message}\n`;
        logArea.scrollTop = logArea.scrollHeight;
    }

    function updatePositionInfo(data) {
        if (!data) {
            positionInfo.innerHTML = '<p>Açık pozisyon yok.</p>';
            return;
        }
        const pnlColor = parseFloat(data.pnl_usdt) >= 0 ? 'success' : 'danger';
        positionInfo.innerHTML = `
            <p><strong>Sembol:</strong> ${data.symbol}</p>
            <p><strong>Büyüklük:</strong> ${data.quantity}</p>
            <p><strong>Giriş Fiyatı:</strong> ${data.entry_price}</p>
            <p><strong>Piyasa Fiyatı:</strong> ${data.mark_price}</p>
            <p><strong>Kâr/Zarar:</strong> <span class="pnl-${pnlColor}">${data.pnl_usdt} USDT</span></p>
            <p><strong>ROI:</strong> <span class="pnl-${pnlColor}">${data.roi_percent}</span></p>
            <p><strong>Stop Loss:</strong> ${data.sl_price}</p>
            <p><strong>Take Profit:</strong> ${data.tp_price}</p>
        `;
    }
    
    // WebSocket bağlantısını kur
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
                // İşlem geçmişini yeniden yükle (API çağrısı ile)
                break;
            case 'stats_update':
                 // İstatistikleri yeniden yükle (API çağrısı ile)
                break;
        }
    };

    ws.onclose = () => {
        statusIndicator.className = 'status-offline';
        addLog('Sunucu bağlantısı koptu. Sayfayı yenileyin.');
    };

    ws.onerror = (error) => {
        addLog('WebSocket hatası oluştu.');
        console.error('WebSocket Error:', error);
    };

    // Buton event listener'ları buraya eklenecek
    // Örneğin: document.getElementById('start-button').addEventListener('click', () => { fetch('/start', {method: 'POST'}); });
});