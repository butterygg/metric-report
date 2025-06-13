import fetch from "node-fetch";
import fs from "fs";

// --- Constants ---
const PROJECTS: { [name: string]: string } = {
  "Rocket Pool": "rocket-pool",
  SuperForm: "superform",
  Balancer: "balancer",
  Beets: "beets",
  Avantis: "avantis",
  Polynomial: "polynomial-protocol",
  "Extra Finance": "extra-finance",
  Gyroscope: "gyroscope-protocol",
  Reservoir: "reservoir-protocol",
  QiDAO: "qidao",
  Silo: "silo-finance",
  Exactly: "exactly",
  "Ionic Protocol": "ionic-protocol",
  "Ironclad Finance": "ironclad-finance",
  "Lets Get HAI": "lets-get-hai",
  "Maverick Protocol": "maverick-protocol",
  Metronome: "metronome",
  "Overnight Finance": "overnight-finance",
  "Peapods Finance": "peapods-finance",
  Sushi: "sushi",
  SynFutures: "synfutures",
  Thales: "thales",
  "TLX Finance": "tlx-finance",
};

const MAJOR_SUPERCHAIN_L2S: Set<string> = new Set([
  "BOB",
  "Base",
  "Ink",
  "Lisk",
  "Mode",
  "Optimism",
  "OP Mainnet",
  "Polynomial",
  "Soneium",
  "Swellchain",
  "Unichain",
  "World Chain",
]);

const METRIC_START_DATE = "2025-03-20";
const METRIC_END_DATE = "2025-06-12";
const TRAILING_DAYS = 7;

// --- Type Definitions for API Response ---
interface TvlDataItem {
  date: number; // Unix timestamp
  totalLiquidityUSD: number;
}

interface ChainTvls {
  [chain: string]: {
    tvl: TvlDataItem[];
  };
}

interface DefiLlamaApiResponse {
  chainTvls: ChainTvls;
}

// --- Helper Functions ---

/**
 * Fetches protocol data from the DefiLlama API.
 * @param {string} protocolSlug The slug of the protocol to fetch.
 * @returns {Promise<DefiLlamaApiResponse>} The API response.
 */
const fetchProtocolData = async (
  protocolSlug: string,
): Promise<DefiLlamaApiResponse> => {
  const apiUrl = `https://api.llama.fi/protocol/${protocolSlug}`;
  try {
    const response = await fetch(apiUrl);
    if (!response.ok) {
      throw new Error(
        `Failed to fetch data for ${protocolSlug}: ${response.statusText}`,
      );
    }
    return (await response.json()) as DefiLlamaApiResponse;
  } catch (error) {
    console.error(
      `Error fetching from DefiLlama API for ${protocolSlug}:`,
      error,
    );
    throw error;
  }
};

/**
 * Calculates the total TVL for a specific date across major Superchain L2s.
 * @param {DefiLlamaApiResponse} data The API response data.
 * @param {Date} date The target date.
 * @returns {number | null} The total TVL in USD, or null if no data found.
 */
const getTvlOnDate = (data: DefiLlamaApiResponse, date: Date): number | null => {
  const targetTimestamp = date.getTime() / 1000;
  let totalTvl = 0;
  let hasData = false;

  for (const chain in data.chainTvls) {
    if (MAJOR_SUPERCHAIN_L2S.has(chain)) {
      const tvlData = data.chainTvls[chain].tvl;
      const dayTvl = tvlData.find((d) => d.date === targetTimestamp);
      if (dayTvl) {
        totalTvl += dayTvl.totalLiquidityUSD;
        hasData = true;
      }
    }
  }
  return hasData ? totalTvl : null;
};

/**
 * Calculates the 7-day trailing average TVL up to a given end date.
 * @param {DefiLlamaApiResponse} data The API response data.
 * @param {string} endDateStr The end date in 'YYYY-MM-DD' format.
 * @returns {number} The 7-day trailing average TVL.
 */
const calculateTrailingAverageTvl = (
  data: DefiLlamaApiResponse,
  endDateStr: string,
): number => {
  let totalTvlForPeriod = 0;
  let nonNullDays = 0;
  const endDate = new Date(`${endDateStr}T00:00:00Z`);

  for (let i = 0; i < TRAILING_DAYS; i++) {
    const date = new Date(endDate);
    date.setUTCDate(date.getUTCDate() - i);
    const dayTvl = getTvlOnDate(data, date);
    if (dayTvl !== null) {
      totalTvlForPeriod += dayTvl;
      nonNullDays++;
    }
  }

  return nonNullDays > 0 ? totalTvlForPeriod / nonNullDays : 0;
};

// --- Main Execution ---

const main = async () => {
  const results: {
    [slug: string]: { start: number; end: number; difference: number } | string;
  } = {};
  const csvRows: string[] = [];

  // CSV header
  csvRows.push("Protocol,Start Value,End Value,Difference");

  for (const name in PROJECTS) {
    const slug = PROJECTS[name];
    console.log(`--- Processing: ${name} (${slug}) ---`);
    try {
      const protocolData = await fetchProtocolData(slug);

      const t_end = calculateTrailingAverageTvl(protocolData, METRIC_END_DATE);
      const t_start = calculateTrailingAverageTvl(
        protocolData,
        METRIC_START_DATE,
      );

      const difference = t_end - t_start;

      results[slug] = {
        start: t_start,
        end: t_end,
        difference,
      };
      console.log(
        `Start: ${t_start.toFixed(2)}, End: ${t_end.toFixed(2)}, Difference: ${difference.toFixed(2)}`,
      );

      // Add to CSV
      csvRows.push(
        `"${name}",${Math.round(t_start)},${Math.round(t_end)},${Math.round(difference)}`,
      );
    } catch (error) {
      results[slug] = "Error processing project";
      console.error(`Failed to process ${name}:`, error);
      csvRows.push(`"${name}",Error,Error`);
    }
    console.log("\n");
  }

  // Write CSV file
  const csvContent = csvRows.join("\n");
  const csvFilename = `protocol_tvl_results_${METRIC_START_DATE}_to_${METRIC_END_DATE}.csv`;
  fs.writeFileSync(csvFilename, csvContent);
  console.log(`CSV file saved as: ${csvFilename}`);

  console.log("\n--- Final Results ---");
  console.log(JSON.stringify(results, null, 2));
};

main().catch((error) => {
  console.error("An error occurred during the script execution:", error);
});
