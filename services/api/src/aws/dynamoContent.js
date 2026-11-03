import { DeleteCommand, GetCommand, PutCommand } from "@aws-sdk/lib-dynamodb";
import { queryPartition } from "./dynamo.js";

const SETTINGS_KEY = { pk: "SETTINGS", sk: "CURRENT" };

/** Settings (SETTINGS/CURRENT), pronunciation fixes (PRONUNCIATION/{word}) and dismissed words (DISMISSED/{word}). */
export function createDynamoContentMethods({ client, tableName }) {
  return {
    async getSettings() {
      const { Item } = await client.send(new GetCommand({ TableName: tableName, Key: SETTINGS_KEY }));
      if (!Item) return null;
      const { voice, voiceEs, speed, mp3Kbps } = Item;
      return { voice, ...(voiceEs !== undefined && { voiceEs }), speed, mp3Kbps };
    },
    async putSettings(settings) {
      await client.send(new PutCommand({ TableName: tableName, Item: { ...SETTINGS_KEY, ...settings, updatedAt: new Date().toISOString() } }));
      return { ...settings };
    },
    async listPronunciations() {
      const pages = await queryPartition(client, tableName, "PRONUNCIATION");
      return pages
        .flatMap((page) => page.Items ?? [])
        .map(({ sk, respelling, updatedAt }) => ({ word: sk, respelling, updatedAt }))
        .sort((a, b) => a.word.localeCompare(b.word));
    },
    async putPronunciation(word, respelling) {
      const pronunciation = { word, respelling, updatedAt: new Date().toISOString() };
      const res = await client.send(
        new PutCommand({
          TableName: tableName,
          Item: { pk: "PRONUNCIATION", sk: word, respelling, updatedAt: pronunciation.updatedAt },
          ReturnValues: "ALL_OLD",
        }),
      );
      return { pronunciation, created: !res.Attributes };
    },
    async deletePronunciation(word) {
      const res = await client.send(
        new DeleteCommand({ TableName: tableName, Key: { pk: "PRONUNCIATION", sk: word }, ReturnValues: "ALL_OLD" }),
      );
      return Boolean(res.Attributes);
    },
    async listDismissed() {
      const pages = await queryPartition(client, tableName, "DISMISSED");
      return pages.flatMap((page) => page.Items ?? []).map((item) => item.sk);
    },
    async addDismissed(word) {
      await client.send(new PutCommand({ TableName: tableName, Item: { pk: "DISMISSED", sk: word, dismissedAt: new Date().toISOString() } }));
    },
  };
}
