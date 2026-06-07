// Чтение заметок из ChaCha20-БД HONOR (node@20 + better-sqlite3-multiple-ciphers).
// argv[2] = путь к копии БД; env HONORPW = пароль; env NODE_PATH к node_modules.
const D = require("better-sqlite3-multiple-ciphers");
const db = new D(process.argv[2], { fileMustExist: true });
db.pragma(`key='${process.env.HONORPW}'`);
const rows = db.prepare(
  "SELECT uuid,title,search_content,html_content,modify_time,delete_flag,type FROM note"
).all();
process.stdout.write(JSON.stringify(rows));
db.close();
