async function askTutor() {
  const question = document.getElementById("question").value;
  if (!question.trim()) {
  alert("Введите вопрос!");
  return;
}


  // Добавить сообщение пользователя
  const chat = document.querySelector(".chat");
  const userMessage = document.createElement("div");
  userMessage.className = "message user";
  userMessage.innerText = question;
  chat.appendChild(userMessage);

  // Очистить поле ввода
  document.getElementById("question").value = "";

  const res = await fetch("http://localhost:5000/ask", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    question,
    subject: localStorage.getItem("subject"),
    mode: localStorage.getItem("mode")
  })
});


  const data = await res.json();


  const aiMessage = document.createElement("div");
  aiMessage.className = "message ai";
  aiMessage.innerText = data.answer;
  chat.appendChild(aiMessage);


  chat.scrollTop = chat.scrollHeight;
}


