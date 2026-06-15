// Плавное исчезновение уведомлений через 5 секунд
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        let alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            let bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Подтверждение удаления в админке
    let deleteButtons = document.querySelectorAll('.delete-place');
    deleteButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            if (!confirm('Удалить это место? Отзывы и избранное также будут удалены.')) {
                e.preventDefault();
            }
        });
    });
});