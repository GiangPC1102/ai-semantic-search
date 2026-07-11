-- CreateTable
CREATE TABLE "brands" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "category" TEXT,
    "subcategory" TEXT,

    CONSTRAINT "brands_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "poi" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "brand_id" TEXT,
    "city" TEXT,
    "district" TEXT,
    "address" TEXT,
    "longitude" DOUBLE PRECISION,
    "latitude" DOUBLE PRECISION,
    "rating" DOUBLE PRECISION,
    "review_count" INTEGER,
    "popularity_score" DOUBLE PRECISION,
    "price_level" TEXT,
    "open_hours" JSONB,
    "description" TEXT,
    "vector_id" TEXT,

    CONSTRAINT "poi_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "attributes" (
    "id" TEXT NOT NULL,
    "attribute_name" TEXT NOT NULL,
    "description" TEXT,
    "vector_id" TEXT,
    "english_name" TEXT,

    CONSTRAINT "attributes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "signals" (
    "id" TEXT NOT NULL,
    "signal_name" TEXT NOT NULL,
    "description" TEXT,
    "vietnam_name" TEXT,

    CONSTRAINT "signals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tags" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,

    CONSTRAINT "tags_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "poi_attributes" (
    "id" TEXT NOT NULL,
    "poi_id" TEXT NOT NULL,
    "attribute_id" TEXT NOT NULL,

    CONSTRAINT "poi_attributes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "poi_tags" (
    "id" TEXT NOT NULL,
    "poi_id" TEXT NOT NULL,
    "tag_id" TEXT NOT NULL,

    CONSTRAINT "poi_tags_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "brands_name_key" ON "brands"("name");

-- CreateIndex
CREATE UNIQUE INDEX "attributes_attribute_name_key" ON "attributes"("attribute_name");

-- CreateIndex
CREATE UNIQUE INDEX "signals_signal_name_key" ON "signals"("signal_name");

-- CreateIndex
CREATE UNIQUE INDEX "tags_name_key" ON "tags"("name");

-- CreateIndex
CREATE UNIQUE INDEX "poi_attributes_poi_id_attribute_id_key" ON "poi_attributes"("poi_id", "attribute_id");

-- CreateIndex
CREATE UNIQUE INDEX "poi_tags_poi_id_tag_id_key" ON "poi_tags"("poi_id", "tag_id");

-- AddForeignKey
ALTER TABLE "poi" ADD CONSTRAINT "poi_brand_id_fkey" FOREIGN KEY ("brand_id") REFERENCES "brands"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "poi_attributes" ADD CONSTRAINT "poi_attributes_poi_id_fkey" FOREIGN KEY ("poi_id") REFERENCES "poi"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "poi_attributes" ADD CONSTRAINT "poi_attributes_attribute_id_fkey" FOREIGN KEY ("attribute_id") REFERENCES "attributes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "poi_tags" ADD CONSTRAINT "poi_tags_poi_id_fkey" FOREIGN KEY ("poi_id") REFERENCES "poi"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "poi_tags" ADD CONSTRAINT "poi_tags_tag_id_fkey" FOREIGN KEY ("tag_id") REFERENCES "tags"("id") ON DELETE CASCADE ON UPDATE CASCADE;
