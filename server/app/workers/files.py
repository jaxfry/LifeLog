import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select, col
from app.core.db import engine
from app.models.files import FileAttachment
from app.core.files import UPLOAD_DIR
from app.core.ai_files import analyze_file_content
from app.core.vector_service import generate_embedding, get_embedding_model_info
from app.core.logger import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 5

async def task_process_file_batch(ctx):
    """
    Worker task to process a batch of unprocessed files.
    Analyzes content with AI and generates embeddings.
    """
    logger.info("Worker: Starting file batch processing")
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Fetch unprocessed files
        query = select(FileAttachment).where(
            FileAttachment.is_processed == False
        ).limit(BATCH_SIZE)
        
        result = await session.execute(query)
        files = result.scalars().all()
        
        if not files:
            logger.info("Worker: No files to process")
            return

        logger.info(f"Worker: Processing batch of {len(files)} files")
        
        # Process in parallel
        tasks = [process_single_file(session, file) for file in files]
        await asyncio.gather(*tasks)
        
        # Commit all changes
        await session.commit()
        logger.info("Worker: Batch processing complete")

async def process_single_file(session: AsyncSession, file: FileAttachment):
    """
    Process a single file: Analyze -> Embed -> Update
    """
    try:
        file_path = UPLOAD_DIR / file.stored_path
        
        # 1. Analyze Content
        logger.info(f"Analyzing file {file.id} ({file.filename})")
        ai_data = await analyze_file_content(
            file_path=file_path,
            mime_type=file.mime_type,
            original_filename=file.filename,
            tags=file.tags,
            category=file.category
        )
        
        if not ai_data:
            logger.warning(f"No AI data generated for file {file.id}")
            # Mark as processed anyway to avoid infinite loops, but maybe add a flag or log it
            file.is_processed = True
            session.add(file)
            return

        # Update AI metadata
        # Ensure we don't overwrite existing keys if we want to merge, but here we likely want to set it
        file.ai_metadata = ai_data
        
        # 2. Generate Embedding
        # Combine relevant text for embedding
        text_to_embed = f"{file.filename}\n"
        if ai_data.get("description"):
            text_to_embed += f"Description: {ai_data['description']}\n"
        if ai_data.get("summary"):
            text_to_embed += f"Summary: {ai_data['summary']}\n"
        if ai_data.get("keywords"):
            text_to_embed += f"Keywords: {', '.join(ai_data['keywords'])}\n"
        if ai_data.get("entities"):
            text_to_embed += f"Entities: {', '.join(ai_data['entities'])}\n"
            
        embedding = await generate_embedding(text_to_embed)
        
        if embedding:
            file.embedding = embedding
            model_info = get_embedding_model_info()
            file.embedding_model = f"{model_info['model']}@{model_info['version']}"
        
        # 3. Mark as Processed
        file.is_processed = True
        session.add(file)
        logger.info(f"Successfully processed file {file.id}")
        
    except Exception as e:
        logger.error(f"Error processing file {file.id}: {e}")
        # We might want to leave is_processed=False to retry, or add a retry count
        # For now, let's leave it to be retried by the next batch run, 
        # but we should be careful about "poison pill" files that always fail.
        # Ideally we'd have a failure count.
