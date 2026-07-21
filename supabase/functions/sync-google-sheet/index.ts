import { createClient } from "npm:@supabase/supabase-js@2.95.0";

type ServiceAccountCredentials = {
  client_email: string;
  private_key: string;
  token_uri?: string;
};

type SheetProperties = {
  sheetId: number;
  title: string;
  index: number;
  hidden?: boolean;
};

type CellValue = string | number | boolean | null;
type SheetRows = CellValue[][];

type StudentRecord = {
  last_name: string;
  first_name: string;
  gender: string;
  grade: string;
  address: string;
  city: string;
  area: string;
  birthday: string;
  sponsor: string;
  contact: string;
  school: string;
  parents: string;
  course: string;
  remarks: string;
  status: string;
  source_row_number: number;
};

type DonorRecord = {
  donor_name: string;
  student_last_name: string;
  student_first_name: string;
  location: string;
  level: string;
  sponsor: string;
  remarks: string;
};

type MovementRecord = {
  category: string;
  student_last_name: string;
  student_first_name: string;
  location: string;
  level: string;
  remarks: string;
};

type CoordinatorRecord = {
  location: string;
  contact_person: string;
  email: string;
  contact_no: string;
  fb_page: string;
  remarks: string;
};

const GOOGLE_SCOPE =
  "https://www.googleapis.com/auth/spreadsheets.readonly";
const FUNCTION_VERSION = "sync-1";

const DEFAULT_SHEETS = {
  master: "Masterlist 2026-2027",
  donor: "List Per Donor 26-27",
  movements: "Movements and Discrepancy Report",
  coordinators: "Coordinator List",
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, apikey, content-type, x-client-info, x-ssm-sync-token",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function base64UrlJson(value: unknown): string {
  return base64Url(new TextEncoder().encode(JSON.stringify(value)));
}

function privateKeyBytes(pem: string): Uint8Array {
  const normalized = pem.replaceAll("\\n", "\n");
  const encoded = normalized
    .replace("-----BEGIN PRIVATE KEY-----", "")
    .replace("-----END PRIVATE KEY-----", "")
    .replace(/\s/g, "");

  if (!encoded) throw new Error("The Google private_key is empty.");
  return Uint8Array.from(atob(encoded), (character) =>
    character.charCodeAt(0)
  );
}

async function googleAccessToken(
  credentials: ServiceAccountCredentials,
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const tokenUri =
    credentials.token_uri || "https://oauth2.googleapis.com/token";
  const unsignedToken = [
    base64UrlJson({ alg: "RS256", typ: "JWT" }),
    base64UrlJson({
      iss: credentials.client_email,
      scope: GOOGLE_SCOPE,
      aud: tokenUri,
      iat: now,
      exp: now + 3600,
    }),
  ].join(".");

  const signingKey = await crypto.subtle.importKey(
    "pkcs8",
    privateKeyBytes(credentials.private_key),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    signingKey,
    new TextEncoder().encode(unsignedToken),
  );
  const assertion = `${unsignedToken}.${base64Url(
    new Uint8Array(signature),
  )}`;

  const response = await fetch(tokenUri, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion,
    }),
  });
  const result = await response.json();

  if (!response.ok || !result.access_token) {
    throw new Error(
      `Google authentication failed (${response.status}): ${
        result.error_description || result.error || "No access token returned"
      }`,
    );
  }
  return result.access_token;
}

function a1SheetName(title: string): string {
  return `'${title.replaceAll("'", "''")}'`;
}

function text(value: CellValue | undefined): string {
  return value === null || value === undefined ? "" : String(value).trim();
}

function normalizedHeader(value: CellValue | undefined): string {
  return text(value).toLowerCase().replace(/\s+/g, " ");
}

function headerMap(row: CellValue[]): Map<string, number> {
  const result = new Map<string, number>();
  row.forEach((value, index) => {
    const key = normalizedHeader(value);
    if (key && !result.has(key)) result.set(key, index);
  });
  return result;
}

function findHeaderRow(rows: SheetRows, required: string[]): number {
  return rows.findIndex((row) => {
    const headers = new Set(row.map(normalizedHeader).filter(Boolean));
    return required.every((name) => headers.has(name));
  });
}

function cell(row: CellValue[], index: number | undefined): string {
  return index === undefined || index < 0 || index >= row.length
    ? ""
    : text(row[index]);
}

function normalizedBirthday(value: CellValue | undefined): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    const milliseconds = Date.UTC(1899, 11, 30) +
      Math.round(value * 86_400_000);
    return new Date(milliseconds).toISOString().slice(0, 10);
  }

  const raw = text(value);
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

  const numericDate = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (numericDate) {
    const [, month, day, year] = numericDate;
    return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
  }

  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime())
    ? ""
    : parsed.toISOString().slice(0, 10);
}

function canonicalName(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function studentIdentity(lastName: string, firstName: string): string {
  return `${canonicalName(lastName)}\u0000${canonicalName(firstName)}`;
}

function findStudentMatch(
  students: StudentRecord[],
  lastName: string,
  firstName: string,
  level: string,
): StudentRecord | undefined {
  const canonicalLast = canonicalName(lastName);
  const canonicalFirst = canonicalName(firstName);
  const exactMatches = students.filter((student) =>
    studentIdentity(student.last_name, student.first_name) ===
      `${canonicalLast}\u0000${canonicalFirst}`
  );
  if (exactMatches.length === 1) return exactMatches[0];

  const sameLastName = students.filter((student) =>
    canonicalName(student.last_name) === canonicalLast
  );
  const firstToken = canonicalFirst.split(" ")[0];
  const safeNameVariants = sameLastName.filter((student) => {
    const studentFirst = canonicalName(student.first_name);
    return studentFirst.split(" ")[0] === firstToken ||
      studentFirst.includes(canonicalFirst) ||
      canonicalFirst.includes(studentFirst);
  });
  if (safeNameVariants.length === 1) return safeNameVariants[0];

  const canonicalLevel = canonicalName(level);
  return sameLastName.length === 1 &&
      Boolean(canonicalLevel) &&
      canonicalName(sameLastName[0].grade) === canonicalLevel
    ? sameLastName[0]
    : undefined;
}

function isCurrencySummary(value: CellValue | undefined): boolean {
  if (typeof value === "number" && Number.isFinite(value)) return true;
  const normalized = text(value);
  return /[$₱]/.test(normalized) ||
    /^(?:php|p)\s*[\d,]+(?:\.\d{2})?$/i.test(normalized);
}

function schoolYearFromSheet(title: string): string {
  const fullYear = title.match(/(20\d{2})\s*-\s*(20\d{2})/);
  if (fullYear) return `${fullYear[1]}-${fullYear[2]}`;
  const shortYear = title.match(/(\d{2})\s*-\s*(\d{2})/);
  if (shortYear) return `20${shortYear[1]}-20${shortYear[2]}`;
  return title;
}

function supabaseAdminClient() {
  const url = Deno.env.get("SUPABASE_URL")?.trim();
  let secretKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")?.trim() || "";
  const namedSecrets = Deno.env.get("SUPABASE_SECRET_KEYS");

  if (namedSecrets) {
    try {
      const parsed = JSON.parse(namedSecrets) as Record<string, string>;
      secretKey = parsed.default || Object.values(parsed)[0] || secretKey;
    } catch {
      throw new Error("SUPABASE_SECRET_KEYS is not valid JSON.");
    }
  }
  if (!url || !secretKey) {
    throw new Error(
      "Supabase did not provide its server-side URL and secret key.",
    );
  }

  return createClient(url, secretKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

function parseMasterlist(rows: SheetRows): {
  records: StudentRecord[];
  duplicateIdentities: number;
} {
  const headerIndex = findHeaderRow(rows, ["last name", "first name"]);
  if (headerIndex < 0) {
    throw new Error("Masterlist headers Last Name and First Name were not found.");
  }

  const headers = headerMap(rows[headerIndex]);
  const lastIndex = headers.get("last name");
  const firstIndex = headers.get("first name");
  const locationIndex = headers.get("location");
  if (lastIndex === undefined || firstIndex === undefined) {
    throw new Error("Masterlist name columns could not be mapped.");
  }

  const records: StudentRecord[] = [];
  let currentArea = "";
  for (let index = headerIndex + 1; index < rows.length; index += 1) {
    const row = rows[index];
    const firstCell = cell(row, 0);
    const lastName = cell(row, lastIndex);
    const firstName = cell(row, firstIndex);

    if (!lastName && !firstName) {
      if (firstCell && !/^\d+(?:\.\d+)?$/.test(firstCell)) {
        currentArea = firstCell;
      }
      continue;
    }
    if (!lastName || !firstName || lastName.toLowerCase() === "last name") {
      continue;
    }

    const grade = cell(row, headers.get("level")) ||
      cell(row, headers.get("grade")) ||
      cell(row, headers.get("grade level"));
    const marker = firstCell.toLowerCase();
    const status = marker === "g" || marker === "graduated" ||
        grade.toLowerCase().includes("graduat")
      ? "Graduated"
      : !marker || marker === "x"
      ? "Inactive/Removed"
      : "Active";

    records.push({
      last_name: lastName,
      first_name: firstName,
      gender: cell(row, headers.get("gender")),
      grade,
      address: cell(row, locationIndex),
      city: cell(
        row,
        locationIndex === undefined ? undefined : locationIndex + 1,
      ),
      area: cell(
        row,
        locationIndex === undefined ? undefined : locationIndex + 2,
      ) || currentArea,
      birthday: normalizedBirthday(row[headers.get("birthday") ?? -1]),
      sponsor: cell(row, headers.get("sponsor")),
      contact: cell(row, headers.get("contact no.")) ||
        cell(row, headers.get("contact")),
      school: cell(row, headers.get("school")),
      parents: cell(row, headers.get("parents")),
      course: cell(row, headers.get("course")),
      remarks: cell(row, headers.get("remarks")),
      status,
      source_row_number: index + 1,
    });
  }

  if (records.length === 0) {
    throw new Error("The current masterlist contains no importable students.");
  }

  const identities = records.map((record) =>
    studentIdentity(record.last_name, record.first_name)
  );
  return {
    records,
    duplicateIdentities: identities.length - new Set(identities).size,
  };
}

function parseCoordinators(rows: SheetRows): CoordinatorRecord[] {
  const headerIndex = findHeaderRow(rows, ["location", "contact person"]);
  if (headerIndex < 0) {
    throw new Error(
      "Coordinator headers Location and Contact Person were not found.",
    );
  }
  const headers = headerMap(rows[headerIndex]);
  const records = rows.slice(headerIndex + 1)
    .filter((row) =>
      cell(row, headers.get("location")) ||
      cell(row, headers.get("contact person"))
    )
    .map((row) => ({
      location: cell(row, headers.get("location")),
      contact_person: cell(row, headers.get("contact person")),
      email: cell(row, headers.get("e-mail")) ||
        cell(row, headers.get("email")),
      contact_no: cell(row, headers.get("contact no.")) ||
        cell(row, headers.get("contact no")),
      fb_page: cell(row, headers.get("fb page")),
      remarks: cell(row, headers.get("remarks")),
    }));
  if (records.length === 0) {
    throw new Error("The coordinator worksheet contains no importable rows.");
  }
  return records;
}

function parseDonorList(
  rows: SheetRows,
  students: StudentRecord[],
): {
  records: DonorRecord[];
  candidates: number;
  matched: number;
  unmatched: number;
  unmatched_rows: number[];
  ignored_summary_rows: number;
} {
  let headers = new Map<string, number>();
  let candidates = 0;
  let matched = 0;
  let ignoredSummaryRows = 0;
  const unmatchedRows: number[] = [];
  const records: DonorRecord[] = [];
  let donorName = "";

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const mapped = headerMap(row);
    if (mapped.has("last name") && mapped.has("first name")) {
      headers = mapped;
      continue;
    }

    const lastName = cell(row, headers.get("last name"));
    const firstName = cell(row, headers.get("first name"));
    const levelIndex = headers.get("level");
    const level = cell(row, levelIndex);
    if (!lastName && !firstName) {
      const possibleDonor = cell(row, 0) || cell(row, 1);
      if (
        possibleDonor &&
        !possibleDonor.toLowerCase().startsWith("ywam students")
      ) {
        donorName = possibleDonor;
      }
      continue;
    }
    if (
      headers.size === 0 || !lastName || !firstName ||
      lastName.toLowerCase() === "last name"
    ) {
      continue;
    }
    if (isCurrencySummary(
      levelIndex === undefined ? undefined : row[levelIndex],
    )) {
      ignoredSummaryRows += 1;
      continue;
    }

    candidates += 1;
    const student = findStudentMatch(students, lastName, firstName, level);
    if (student) {
      matched += 1;
      records.push({
        donor_name: donorName,
        student_last_name: student.last_name,
        student_first_name: student.first_name,
        location: cell(row, headers.get("location")),
        level,
        sponsor: cell(row, headers.get("sponsor")),
        remarks: cell(row, headers.get("remarks")),
      });
    } else {
      unmatchedRows.push(index + 1);
    }
  }
  return {
    records,
    candidates,
    matched,
    unmatched: candidates - matched,
    unmatched_rows: unmatchedRows,
    ignored_summary_rows: ignoredSummaryRows,
  };
}

function parseMovements(
  rows: SheetRows,
  students: StudentRecord[],
): {
  records: MovementRecord[];
  candidates: number;
  matched: number;
  unmatched: number;
  unmatched_rows: number[];
} {
  let headers = new Map<string, number>();
  let candidates = 0;
  let matched = 0;
  const unmatchedRows: number[] = [];
  const records: MovementRecord[] = [];
  let category = "";

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const mapped = headerMap(row);
    if (
      mapped.has("last name") &&
      (mapped.has("first name") || mapped.has("name"))
    ) {
      headers = mapped;
      continue;
    }

    const lastName = cell(row, headers.get("last name"));
    const firstName = cell(
      row,
      headers.has("first name")
        ? headers.get("first name")
        : headers.get("name"),
    );
    const level = cell(row, headers.get("level"));
    if (!lastName && !firstName) {
      const possibleCategory = cell(row, 0);
      if (possibleCategory) category = possibleCategory;
      continue;
    }
    if (
      headers.size === 0 || !lastName || !firstName ||
      lastName.toLowerCase() === "last name"
    ) {
      continue;
    }

    candidates += 1;
    const student = findStudentMatch(students, lastName, firstName, level);
    if (student) {
      matched += 1;
      records.push({
        category,
        student_last_name: student.last_name,
        student_first_name: student.first_name,
        location: cell(row, headers.get("location")),
        level,
        remarks: cell(row, headers.get("remarks")),
      });
    } else {
      unmatchedRows.push(index + 1);
    }
  }
  return {
    records,
    candidates,
    matched,
    unmatched: candidates - matched,
    unmatched_rows: unmatchedRows,
  };
}

Deno.serve(async (request: Request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return jsonResponse({ ok: false, error: "Use a POST request." }, 405);
  }

  try {
    const requestBody = await request.json().catch(() => ({})) as {
      mode?: string;
      confirmation?: string;
    };
    const mode = requestBody.mode || "dry-run";
    if (!["dry-run", "commit"].includes(mode)) {
      return jsonResponse({
        ok: false,
        error: "mode must be either dry-run or commit.",
      }, 400);
    }
    if (mode === "commit") {
      const expectedToken = Deno.env.get("SSM_SHEET_SYNC_TOKEN");
      const suppliedToken = request.headers.get("x-ssm-sync-token");
      if (!expectedToken) {
        return jsonResponse({
          ok: false,
          error: "Missing SSM_SHEET_SYNC_TOKEN Edge Function secret.",
        }, 500);
      }
      if (!suppliedToken || suppliedToken !== expectedToken) {
        return jsonResponse({
          ok: false,
          error: "Valid sheet sync token required.",
        }, 401);
      }
      if (requestBody.confirmation !== "SYNC_SSM_MASTERLIST") {
        return jsonResponse({
          ok: false,
          error: "Commit confirmation phrase is missing or invalid.",
        }, 400);
      }
    }

    const rawCredentials = Deno.env.get("GOOGLE_SERVICE_ACCOUNT_JSON");
    const spreadsheetId = Deno.env.get("GOOGLE_SHEET_ID")?.trim();

    if (!rawCredentials) {
      throw new Error(
        "Missing GOOGLE_SERVICE_ACCOUNT_JSON Edge Function secret.",
      );
    }
    if (!spreadsheetId) {
      throw new Error("Missing GOOGLE_SHEET_ID Edge Function secret.");
    }

    const credentials = JSON.parse(
      rawCredentials,
    ) as ServiceAccountCredentials;
    if (!credentials.client_email || !credentials.private_key) {
      throw new Error(
        "GOOGLE_SERVICE_ACCOUNT_JSON must contain client_email and private_key.",
      );
    }

    const accessToken = await googleAccessToken(credentials);
    const googleHeaders = { Authorization: `Bearer ${accessToken}` };

    const metadataUrl = new URL(
      `https://sheets.googleapis.com/v4/spreadsheets/${
        encodeURIComponent(spreadsheetId)
      }`,
    );
    metadataUrl.searchParams.set(
      "fields",
      "properties(title),sheets(properties(sheetId,title,index,hidden))",
    );
    const metadataResponse = await fetch(metadataUrl, {
      headers: googleHeaders,
    });
    const metadata = await metadataResponse.json();
    if (!metadataResponse.ok) {
      throw new Error(
        `Google Sheets metadata request failed (${metadataResponse.status}): ${
          metadata.error?.message || "Unknown error"
        }`,
      );
    }

    const sheetProperties: SheetProperties[] = (metadata.sheets || [])
      .map((sheet: { properties: SheetProperties }) => sheet.properties)
      .sort((left: SheetProperties, right: SheetProperties) =>
        left.index - right.index
      );
    if (sheetProperties.length === 0) {
      throw new Error("The Google workbook contains no readable tabs.");
    }

    const valuesUrl = new URL(
      `https://sheets.googleapis.com/v4/spreadsheets/${
        encodeURIComponent(spreadsheetId)
      }/values:batchGet`,
    );
    valuesUrl.searchParams.set("majorDimension", "ROWS");
    valuesUrl.searchParams.set("valueRenderOption", "UNFORMATTED_VALUE");
    valuesUrl.searchParams.set("dateTimeRenderOption", "SERIAL_NUMBER");
    for (const sheet of sheetProperties) {
      valuesUrl.searchParams.append("ranges", a1SheetName(sheet.title));
    }

    const valuesResponse = await fetch(valuesUrl, {
      headers: googleHeaders,
    });
    const valuesResult = await valuesResponse.json();
    if (!valuesResponse.ok) {
      throw new Error(
        `Google Sheets values request failed (${valuesResponse.status}): ${
          valuesResult.error?.message || "Unknown error"
        }`,
      );
    }

    const valueRanges = valuesResult.valueRanges || [];
    const rowsByTitle = new Map<string, SheetRows>();
    const sheets = sheetProperties.map((sheet, index) => {
      const rows: SheetRows = valueRanges[index]?.values || [];
      rowsByTitle.set(sheet.title, rows);
      return {
        title: sheet.title,
        hidden: Boolean(sheet.hidden),
        populated_rows: rows.length,
        populated_columns: rows.reduce(
          (maximum, row) => Math.max(maximum, row.length),
          0,
        ),
      };
    });

    const selectedSheets = {
      master: Deno.env.get("GOOGLE_MASTER_SHEET")?.trim() ||
        DEFAULT_SHEETS.master,
      donor: Deno.env.get("GOOGLE_DONOR_SHEET")?.trim() ||
        DEFAULT_SHEETS.donor,
      movements: Deno.env.get("GOOGLE_MOVEMENTS_SHEET")?.trim() ||
        DEFAULT_SHEETS.movements,
      coordinators: Deno.env.get("GOOGLE_COORDINATOR_SHEET")?.trim() ||
        DEFAULT_SHEETS.coordinators,
    };
    const requiredRows = (title: string): SheetRows => {
      const rows = rowsByTitle.get(title);
      if (!rows) throw new Error(`Required worksheet not found: ${title}`);
      return rows;
    };

    const masterlist = parseMasterlist(requiredRows(selectedSheets.master));
    const donors = parseDonorList(
      requiredRows(selectedSheets.donor),
      masterlist.records,
    );
    const movements = parseMovements(
      requiredRows(selectedSheets.movements),
      masterlist.records,
    );
    const coordinators = parseCoordinators(
      requiredRows(selectedSheets.coordinators),
    );
    const activeStudents = masterlist.records.filter((record) =>
      record.status === "Active"
    ).length;
    const graduatedStudents = masterlist.records.filter((record) =>
      record.status === "Graduated"
    ).length;
    const ignoredSheets = sheets
      .map((sheet) => sheet.title)
      .filter((title) => !Object.values(selectedSheets).includes(title));

    const proposedImport = {
      students: {
        total: masterlist.records.length,
        active: activeStudents,
        inactive_or_removed: masterlist.records.length - activeStudents -
          graduatedStudents,
        graduated: graduatedStudents,
        duplicate_name_pairs: masterlist.duplicateIdentities,
      },
      donor_students: {
        candidates: donors.candidates,
        matched: donors.matched,
        unmatched: donors.unmatched,
        unmatched_rows: donors.unmatched_rows,
        ignored_summary_rows: donors.ignored_summary_rows,
      },
      movements: {
        candidates: movements.candidates,
        matched: movements.matched,
        unmatched: movements.unmatched,
        unmatched_rows: movements.unmatched_rows,
      },
      coordinators: coordinators.length,
    };

    if (mode === "commit") {
      if (masterlist.duplicateIdentities > 0) {
        throw new Error(
          "Commit stopped because the masterlist contains duplicate names.",
        );
      }
      if (donors.unmatched > 5) {
        throw new Error(
          "Commit stopped because too many donor students are unmatched.",
        );
      }
      if (movements.unmatched > 0) {
        throw new Error(
          "Commit stopped because one or more movement students are unmatched.",
        );
      }

      const studentPayload = masterlist.records.map((record) => ({
        ...record,
        source_student_id:
          `${spreadsheetId}:${selectedSheets.master}:${record.source_row_number}`,
        source_sheet_name: selectedSheets.master,
      }));
      const supabase = supabaseAdminClient();
      const { data, error } = await supabase.rpc(
        "sync_google_workbook_transactional",
        {
          p_students: studentPayload,
          p_donor_school_year: schoolYearFromSheet(selectedSheets.donor),
          p_donor_students: donors.records,
          p_movements: movements.records,
          p_coordinators: coordinators,
        },
      );
      if (error) {
        throw new Error(`Supabase workbook transaction failed: ${error.message}`);
      }

      return jsonResponse({
        ok: true,
        mode: "commit",
        version: FUNCTION_VERSION,
        message: "Google workbook synchronized successfully.",
        workbook: metadata.properties?.title || "Untitled workbook",
        database_result: data,
        source_summary: proposedImport,
        excluded_donor_rows: donors.unmatched_rows,
      });
    }

    return jsonResponse({
      ok: true,
      mode: "dry-run",
      version: FUNCTION_VERSION,
      message: "Workbook parsing succeeded. No database records were changed.",
      workbook: metadata.properties?.title || "Untitled workbook",
      sheet_count: sheets.length,
      selected_sheets: selectedSheets,
      proposed_import: proposedImport,
      ignored_sheets: ignoredSheets,
    });
  } catch (error) {
    console.error(error);
    return jsonResponse({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }, 500);
  }
});
