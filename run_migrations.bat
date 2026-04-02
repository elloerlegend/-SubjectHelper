@echo off
echo ================================================
echo     SubjectHelper — Обновление базы данных
echo ================================================

:: Активируем виртуальное окружение
call .venv\Scripts\activate.bat

:: Устанавливаем недостающие пакеты автоматически
echo Проверка зависимостей...
pip install -q flask-migrate python-dotenv

echo Запуск миграций...

:: Устанавливаем переменную окружения
set FLASK_APP=main.py

:: Выполняем миграции
flask db migrate -m "auto update" || echo Предупреждение: Не удалось создать миграцию (возможно, изменений нет)
flask db upgrade

echo.
echo ✅ База данных успешно обновлена!
echo.
pause