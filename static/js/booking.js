
document.addEventListener("DOMContentLoaded", function () {
    const dateSelect = document.getElementById("tour_date_id");
    const participantsInput = document.getElementById("participants");
    const totalElement = document.getElementById("booking-total");
    const availability = document.getElementById("booking-availability");

    if (!dateSelect || !participantsInput || !totalElement) {
        return;
    }

    const price = Number(totalElement.dataset.price);

    function updateBooking() {
        const selectedOption = dateSelect.selectedOptions[0];
        const places = Number(selectedOption?.dataset.places || 0);
        const participants = Number(participantsInput.value) || 1;

        if (places > 0) {
            participantsInput.max = places;
            availability.textContent = `Свободных мест: ${places}`;
        } else {
            availability.textContent = "Выберите дату путешествия";
        }

        const total = price * participants;

        totalElement.textContent =
            new Intl.NumberFormat("ru-RU", {
                style: "currency",
                currency: "RUB",
                maximumFractionDigits: 0
            }).format(total);
    }

    dateSelect.addEventListener("change", updateBooking);
    participantsInput.addEventListener("input", updateBooking);

    updateBooking();
});
