/**
 * Circular upload webhook (replaces the Google Form submission).
 *
 * Script Properties (Project Settings > Script Properties):
 *   WEBHOOK_TOKEN      shared secret, same as FORM_WEBHOOK_TOKEN in .env
 *   UPLOAD_FOLDER_ID   Drive folder that receives the PDFs
 *                      1f6SHKc1CQCkwFjnaZ5oVmHRPFf29UODBYEuitBCbGxNJFIV3-Xy8ae8JNnXC6j3K0_8zvEhO
 *   RESPONSE_SHEET_ID  spreadsheet that receives one row per circular
 *                      1qATwj8rCRpyzpto_-ErKEbjKrEVEfAp0DLGJE7K47Go
 *   RESPONSE_TAB       tab name inside that spreadsheet: Form Responses 3
 *
 * Deploy > New deployment > Web app: Execute as "Me", Who has access "Anyone".
 * Copy the /exec URL into FORM_WEBHOOK_URL in .env.
 */

var ALLOWED_TYPES = ['Nalco', 'Balco', 'Hindalco'];
var MAX_BASE64_LENGTH = 28 * 1024 * 1024; // ~20 MB decoded
var DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function doPost(e) {
  var props = PropertiesService.getScriptProperties();
  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply_({ ok: false, error: 'invalid JSON' });
  }
  if (!body || typeof body !== 'object') {
    return reply_({ ok: false, error: 'invalid JSON' });
  }

  if (!body.token || body.token !== props.getProperty('WEBHOOK_TOKEN')) {
    return reply_({ ok: false, error: 'unauthorized' });
  }
  if (!body.type || !body.date || !body.filename || !body.pdf_base64) {
    return reply_({ ok: false, error: 'missing field' });
  }
  if (ALLOWED_TYPES.indexOf(body.type) < 0) {
    return reply_({ ok: false, error: 'invalid type' });
  }
  if (!DATE_PATTERN.test(String(body.date))) {
    return reply_({ ok: false, error: 'invalid date' });
  }
  if (String(body.pdf_base64).length > MAX_BASE64_LENGTH) {
    return reply_({ ok: false, error: 'file too large' });
  }

  var parts = String(body.date).split('-');
  var year = Number(parts[0]);
  var month = Number(parts[1]);
  var day = Number(parts[2]);
  var circularDate = new Date(year, month - 1, day);
  if (
    isNaN(circularDate.getTime()) ||
    circularDate.getFullYear() !== year ||
    circularDate.getMonth() !== month - 1 ||
    circularDate.getDate() !== day
  ) {
    return reply_({ ok: false, error: 'invalid date' });
  }

  var bytes;
  try {
    bytes = Utilities.base64Decode(body.pdf_base64);
  } catch (err) {
    return reply_({ ok: false, error: 'invalid PDF' });
  }
  if (bytes.length < 5 || String.fromCharCode.apply(null, bytes.slice(0, 5)) !== '%PDF-') {
    return reply_({ ok: false, error: 'invalid PDF' });
  }

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
  } catch (err) {
    console.error(err);
    return reply_({ ok: false, error: 'busy' });
  }

  try {
    var folder = DriveApp.getFolderById(props.getProperty('UPLOAD_FOLDER_ID'));
    if (!folder) {
      return reply_({ ok: false, error: 'upload folder not found' });
    }
    var blob = Utilities.newBlob(bytes, 'application/pdf', String(body.filename));
    var file = folder.createFile(blob);

    var sheet = SpreadsheetApp.openById(props.getProperty('RESPONSE_SHEET_ID'))
      .getSheetByName(props.getProperty('RESPONSE_TAB'));
    if (!sheet) {
      return reply_({ ok: false, error: 'response tab not found' });
    }
    // Same column order as the old form: Timestamp, Circular Type, Upload Circular, Select Date
    sheet.appendRow([new Date(), body.type, file.getUrl(), circularDate]);

    return reply_({ ok: true, url: file.getUrl() });
  } catch (err) {
    console.error(err);
    return reply_({ ok: false, error: 'upload failed' });
  } finally {
    lock.releaseLock();
  }
}

function reply_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
