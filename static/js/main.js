// ========================================
// フラッシュメッセージの自動非表示
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(alert => {
        // 3秒後に自動で消える
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            
            setTimeout(() => {
                alert.remove();
            }, 500);
        }, 3000);
    });
});

// ========================================
// 在庫更新フォームの確認
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const stockForms = document.querySelectorAll('.stock-form');
    
    stockForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const quantityInput = form.querySelector('input[name="quantity_delta"]');
            const reasonSelect = form.querySelector('select[name="reason"]');
            
            if (!quantityInput.value || quantityInput.value == 0) {
                e.preventDefault();
                alert('数量を入力してください（0以外）');
                return false;
            }
            
            if (!reasonSelect.value) {
                e.preventDefault();
                alert('理由を選択してください');
                return false;
            }
        });
    });
});

// ========================================
// 通知解決の確認
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const resolveLinks = document.querySelectorAll('a[href*="resolve_notification"]');
    
    resolveLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if (!confirm('この通知を解決済みにしますか？')) {
                e.preventDefault();
            }
        });
    });
});

// ========================================
// 在庫カードのアニメーション
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const cards = document.querySelectorAll('.item-card');
    
    cards.forEach((card, index) => {
        setTimeout(() => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.transition = 'opacity 0.5s, transform 0.5s';
            
            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 50);
        }, index * 50);
    });
});

// ========================================
// 在庫低下カードの強調表示
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const lowStockCards = document.querySelectorAll('.item-card.low-stock');
    
    lowStockCards.forEach(card => {
        // 点滅アニメーション
        setInterval(() => {
            card.style.transition = 'background-color 0.5s';
            card.style.backgroundColor = card.style.backgroundColor === 'rgb(255, 245, 245)' ? '#ffe5e5' : '#fff5f5';
        }, 2000);
    });
});

// ========================================
// 数量入力の便利機能
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const quantityInputs = document.querySelectorAll('input[name="quantity_delta"]');
    
    quantityInputs.forEach(input => {
        // プラスボタン（よく使う数値のショートカット）
        const container = input.parentElement;
        
        // フォーカス時にすべて選択
        input.addEventListener('focus', function() {
            this.select();
        });
    });
});

// ========================================
// ページ読み込み時のスムーズスクロール
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    // 通知がある場合は通知エリアにスクロール
    const notifications = document.querySelector('.notifications');
    if (notifications) {
        setTimeout(() => {
            notifications.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 500);
    }
});

// ========================================
// コンソールログ（開発用）
// ========================================
console.log('📦 在庫管理アプリ - JavaScript loaded');
// ========================================
// クイックボタンで数量を加算・減算
// ========================================
document.addEventListener('DOMContentLoaded', function() {
    const quickButtons = document.querySelectorAll('.quick-btn');
    
    quickButtons.forEach(button => {
        button.addEventListener('click', function() {
            const value = parseFloat(this.dataset.value);
            const form = this.closest('.stock-form');
            const input = form.querySelector('input[name="quantity_delta"]');
            
            // 現在の値を取得（空なら0）
            let currentValue = parseFloat(input.value) || 0;
            
            // 値を加算・減算
            let newValue = currentValue + value;
            
            // 小数点第1位まで四捨五入
            newValue = Math.round(newValue * 10) / 10;
            
            // 値を設定
            input.value = newValue;
            
            // ボタンを一時的に強調
            this.style.transform = 'scale(1.1)';
            setTimeout(() => {
                this.style.transform = '';
            }, 200);
        });
    });
    
    // リセットボタン
    const resetButtons = document.querySelectorAll('.btn-reset');
    resetButtons.forEach(button => {
        button.addEventListener('click', function() {
            const form = this.closest('.stock-form');
            const input = form.querySelector('input[name="quantity_delta"]');
            input.value = '';
        });
    });
});
// ========================================
// カテゴリーアコーディオンの開閉
// ========================================
function toggleCategory(categoryId) {
    const content = document.getElementById('content-' + categoryId);
    const arrow = document.getElementById('arrow-' + categoryId);
    
    if (content.style.display === 'none') {
        // 開く
        content.style.display = 'block';
        arrow.classList.add('open');
    } else {
        // 閉じる
        content.style.display = 'none';
        arrow.classList.remove('open');
    }
}

// ページ読み込み時に最初のカテゴリーを開く
document.addEventListener('DOMContentLoaded', function() {
    const firstCategory = document.querySelector('.category-accordion');
    if (firstCategory) {
        const categoryId = firstCategory.querySelector('.category-header').getAttribute('onclick').match(/\d+/)[0];
        toggleCategory(categoryId);
    }
});