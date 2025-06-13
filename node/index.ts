import fetch from "node-fetch";

// --- Constants ---
const PROJECTS: { [name: string]: string } = {
  "Rocket Pool": "rocket-pool",
  SuperForm: "superform",
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
const fetchProtocolData = async (protocolSlug: string): Promise<DefiLlamaApiResponse> => {
  const apiUrl = `https://api.llama.fi/protocol/${protocolSlug}`;
  try {
    const response = await fetch(apiUrl);
    if (!response.ok) {
      throw new Error(`Failed to fetch data for ${protocolSlug}: ${response.statusText}`);
    }
    return (await response.json()) as DefiLlamaApiResponse;
  } catch (error) {
    console.error(`Error fetching from DefiLlama API for ${protocolSlug}:`, error);
    throw error;
  }
};

/**
 * Calculates the total TVL for a specific date across major Superchain L2s.
 * @param {DefiLlamaApiResponse} data The API response data.
 * @param {Date} date The target date.
 * @returns {number} The total TVL in USD.
 */
const getTvlOnDate = (data: DefiLlamaApiResponse, date: Date): number => {
  let totalTvl = 0;
  const targetTimestamp = date.getTime() / 1000;

  for (const chain in data.chainTvls) {
    const chainName = chain.split("-")[0]; // Handle chains like 'Base-staking'
    if (MAJOR_SUPERCHAIN_L2S.has(chainName)) {
      const tvlData = data.chainTvls[chain].tvl;
      const dayTvl = tvlData.find((d) => d.date === targetTimestamp);
      if (dayTvl) {
        totalTvl += dayTvl.totalLiquidityUSD;
      }
    }
  }
  return totalTvl;
};

/**
 * Calculates the 7-day trailing average TVL up to a given end date.
 * @param {DefiLlamaApiResponse} data The API response data.
 * @param {string} endDateStr The end date in 'YYYY-MM-DD' format.
 * @returns {number} The 7-day trailing average TVL.
 */
const calculateTrailingAverageTvl = (data: DefiLlamaApiResponse, endDateStr: string): number => {
  let totalTvlForPeriod = 0;
  const endDate = new Date(`${endDateStr}T00:00:00Z`);

  for (let i = 0; i < TRAILING_DAYS; i++) {
    const date = new Date(endDate);
    date.setUTCDate(date.getUTCDate() - i);
    totalTvlForPeriod += getTvlOnDate(data, date);
  }

  return totalTvlForPeriod / TRAILING_DAYS;
};

// --- Main Execution ---

const main = async () => {
  const results: { [slug: string]: number | string } = {};

  for (const name in PROJECTS) {
    const slug = PROJECTS[name];
    console.log(`--- Processing: ${name} (${slug}) ---`);
    try {
      const protocolData = await fetchProtocolData(slug);

      const t_end = calculateTrailingAverageTvl(protocolData, METRIC_END_DATE);
      const t_start = calculateTrailingAverageTvl(protocolData, METRIC_START_DATE);

      console.log(`T(${METRIC_END_DATE}) = $${t_end.toFixed(2)}`);
      console.log(`T(${METRIC_START_DATE}) = $${t_start.toFixed(2)}`);

      const difference = t_end - t_start;

      results[slug] = difference;
      console.log(`Result for ${slug}: ${difference}`);
    } catch (error) {
      results[slug] = "Error processing project";
      console.error(`Failed to process ${name}:`, error);
    }
    console.log("\n");
  }

  console.log("\n--- Final Results ---");
  console.log(JSON.stringify(results, null, 2));
};

main().catch((error) => {
  console.error("An error occurred during the script execution:", error);
});
