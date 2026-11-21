import http from "k6/http";
import exec from "k6/execution";
import { Counter, Rate, Trend } from "k6/metrics";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000/api/v1";
const PROFILE = __ENV.SCENARIO || "mixed";
const RATE = Number(__ENV.RATE || 1);
const DURATION = __ENV.DURATION || "30s";
const PRE_ALLOCATED_VUS = Number(__ENV.PRE_ALLOCATED_VUS || Math.max(20, RATE * 2));
const MAX_VUS = Number(__ENV.MAX_VUS || Math.max(200, RATE * 8));
const SUMMARY_PATH = __ENV.SUMMARY_PATH || "load-summary.json";
const PASSWORD = __ENV.DEMO_PASSWORD;

const businessDuration = new Trend("business_duration", true);
const businessErrors = new Rate("business_errors");
const businessRequests = new Counter("business_requests");
const expectedStatuses = http.expectedStatuses(200, 201, 409);

export const options = {
  discardResponseBodies: false,
  scenarios: {
    requests: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
      gracefulStop: "5s",
    },
  },
  thresholds: {
    business_duration: ["p(95)<500"],
    business_errors: ["rate<0.01"],
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "max"],
};

function login(loginName) {
  const response = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ login: loginName, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { operation: "setup_login" } },
  );
  if (response.status !== 200) {
    throw new Error(`Login ${loginName} failed with HTTP ${response.status}: ${response.body}`);
  }
  return response.json("access_token");
}

function authHeaders(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    responseCallback: expectedStatuses,
  };
}

function jsonItems(response) {
  try {
    return response.json("items") || [];
  } catch (_error) {
    return [];
  }
}

export function setup() {
  if (!PASSWORD) {
    throw new Error("Set DEMO_PASSWORD before running the load test");
  }
  const customer = login("customer");
  const support = login("support");
  const admin = login("admin");

  const customerTickets = jsonItems(
    http.get(`${BASE_URL}/tickets?limit=100`, authHeaders(customer)),
  );
  const supportTickets = jsonItems(
    http.get(`${BASE_URL}/tickets?limit=100`, authHeaders(support)),
  );
  const categories = jsonItems(
    http.get(`${BASE_URL}/categories?limit=100`, authHeaders(customer)),
  );
  const adminCategories = jsonItems(
    http.get(`${BASE_URL}/admin/categories?limit=100`, authHeaders(admin)),
  );

  if (!customerTickets.length || !supportTickets.length || !categories.length || !adminCategories.length) {
    throw new Error("The work dataset is missing tickets or categories; run the work seed first");
  }

  const openCustomerTickets = customerTickets.filter((ticket) => ticket.status !== "closed");
  const newSupportTickets = supportTickets.filter((ticket) => ticket.status === "new");
  return {
    tokens: { customer, support, admin },
    customerTicketIds: customerTickets.map((ticket) => ticket.id),
    openCustomerTicketIds: (openCustomerTickets.length ? openCustomerTickets : customerTickets).map(
      (ticket) => ticket.id,
    ),
    supportTicketIds: supportTickets.map((ticket) => ticket.id),
    newSupportTicketIds: (newSupportTickets.length ? newSupportTickets : supportTickets).map(
      (ticket) => ticket.id,
    ),
    categoryIds: categories.map((category) => category.id),
    adminCategoryIds: adminCategories.map((category) => category.id),
  };
}

function choose(values, iteration, salt = 0) {
  return values[(iteration * 37 + salt) % values.length];
}

function request(operation, method, path, token, body = null) {
  const params = authHeaders(token);
  params.tags = { operation, profile: PROFILE };
  const response = http.request(method, `${BASE_URL}${path}`, body === null ? null : JSON.stringify(body), params);
  const accepted = response.status === 200 || response.status === 201 || response.status === 409;
  check(response, { [`${operation}: expected status`]: () => accepted }, { operation, profile: PROFILE });
  businessDuration.add(response.timings.duration, { operation, profile: PROFILE });
  businessErrors.add(!accepted, { operation, profile: PROFILE });
  businessRequests.add(1, { operation, profile: PROFILE });
}

const weightedOperations = [
  ["current_user", 2],
  ["categories", 8],
  ["create_ticket", 5],
  ["list_tickets", 22],
  ["get_ticket", 21],
  ["list_comments", 16],
  ["add_comment", 8],
  ["change_status", 4],
  ["summary", 1],
  ["admin_categories", 3],
  ["create_category", 1],
  ["patch_category", 1],
  ["admin_norms", 2],
  ["put_norm", 1],
  ["admin_users", 2],
  ["create_user", 1],
  ["patch_user", 2],
];

const mixedSchedule = weightedOperations.flatMap(([name, weight]) => Array(weight).fill(name));

function mixed(data, iteration) {
  const operation = mixedSchedule[(iteration * 37 + 17) % mixedSchedule.length];
  const customer = data.tokens.customer;
  const support = data.tokens.support;
  const admin = data.tokens.admin;
  const ticketId = choose(data.supportTicketIds, iteration, 3);
  const customerTicketId = choose(data.customerTicketIds, iteration, 5);
  const openCustomerTicketId = choose(data.openCustomerTicketIds, iteration, 7);
  const newSupportTicketId = choose(data.newSupportTicketIds, iteration, 11);
  const categoryId = choose(data.categoryIds, iteration, 13);
  const adminCategoryId = choose(data.adminCategoryIds, iteration, 19);
  const suffix = `${Date.now()}_${exec.vu.idInTest}_${iteration}`;

  switch (operation) {
    case "current_user":
      request(operation, "GET", "/auth/me", customer);
      break;
    case "categories":
      request(operation, "GET", "/categories?limit=20", customer);
      break;
    case "create_ticket":
      request(operation, "POST", "/tickets", customer, {
        category_id: categoryId,
        title: `Нагрузочная заявка ${suffix}`,
        body: `Проверка смешанного профиля ${suffix}`,
      });
      break;
    case "list_tickets":
      request(operation, "GET", "/tickets?limit=20", support);
      break;
    case "get_ticket":
      request(operation, "GET", `/tickets/${ticketId}`, support);
      break;
    case "list_comments":
      request(operation, "GET", `/tickets/${customerTicketId}/comments?limit=20`, customer);
      break;
    case "add_comment":
      request(operation, "POST", `/tickets/${openCustomerTicketId}/comments`, customer, {
        body: `Дополнение из нагрузочного теста ${suffix}`,
      });
      break;
    case "change_status":
      request(operation, "PATCH", `/tickets/${newSupportTicketId}/status`, support, {
        status: "in_progress",
      });
      break;
    case "summary":
      request(operation, "GET", "/summary", support);
      break;
    case "admin_categories":
      request(operation, "GET", "/admin/categories?limit=20", admin);
      break;
    case "create_category":
      request(operation, "POST", "/admin/categories", admin, {
        name: `Нагрузочная категория ${suffix}`,
        description: "Создана смешанным профилем k6",
        response_seconds: 3600,
      });
      break;
    case "patch_category":
      request(operation, "PATCH", `/admin/categories/${adminCategoryId}`, admin, {
        description: `Проверено нагрузкой ${suffix}`,
      });
      break;
    case "admin_norms":
      request(operation, "GET", "/admin/norms?limit=20", admin);
      break;
    case "put_norm":
      request(operation, "PUT", `/admin/norms/${adminCategoryId}`, admin, {
        response_seconds: 3600,
      });
      break;
    case "admin_users":
      request(operation, "GET", "/admin/users?limit=20", admin);
      break;
    case "create_user":
      request(operation, "POST", "/admin/users", admin, {
        login: `u${suffix}`.toLowerCase(),
        display_name: `Пользователь ${suffix}`,
        role: "customer",
        password: PASSWORD,
      });
      break;
    case "patch_user":
      request(operation, "PATCH", "/admin/users/customer", admin, {
        display_name: `Демо пользователь ${iteration % 100}`,
      });
      break;
    default:
      throw new Error(`Unknown operation ${operation}`);
  }
}

export default function (data) {
  const iteration = exec.scenario.iterationInTest;
  if (PROFILE === "heavy") {
    request("summary", "GET", "/summary", data.tokens.support);
    return;
  }
  if (PROFILE !== "mixed") {
    throw new Error(`SCENARIO must be mixed or heavy, got ${PROFILE}`);
  }
  mixed(data, iteration);
}

export function handleSummary(data) {
  return {
    stdout: `${textSummary(data)}\n`,
    [SUMMARY_PATH]: JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const metrics = data.metrics;
  const duration = metrics.business_duration && metrics.business_duration.values;
  const errors = metrics.business_errors && metrics.business_errors.values;
  const requests = metrics.business_requests && metrics.business_requests.values;
  const iterations = metrics.iterations && metrics.iterations.values;
  const dropped = metrics.dropped_iterations && metrics.dropped_iterations.values;
  if (!duration) return "No business requests were completed";
  return [
    `profile=${PROFILE} rate=${RATE}/s duration=${DURATION}`,
    `requests=${requests ? requests.count : 0} iterations=${iterations ? iterations.count : 0}`,
    `median=${duration.med.toFixed(2)}ms p95=${duration["p(95)"].toFixed(2)}ms max=${duration.max.toFixed(2)}ms`,
    `errors=${errors ? (errors.rate * 100).toFixed(3) : "0.000"}% dropped=${dropped ? dropped.count : 0}`,
  ].join("\n");
}
