from datetime import datetime
import httpx
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.settings import settings


async def fetch_items() -> list[dict]:
    auth = httpx.BasicAuth(
        username=settings.autochecker_email,
        password=settings.autochecker_password
    )
    
    url = f"{settings.autochecker_api_url}/api/items"
    
    async with httpx.AsyncClient(auth=auth) as client:
        response = await client.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch items: {response.status_code} - {response.text}")
        
        return response.json()


async def fetch_logs(since: datetime | None = None) -> list[dict]:
    auth = httpx.BasicAuth(
        username=settings.autochecker_email,
        password=settings.autochecker_password
    )
    
    all_logs = []
    current_since = since
    has_more = True
    page = 0
    
    async with httpx.AsyncClient(auth=auth) as client:
        while has_more:
            url = f"{settings.autochecker_api_url}/api/logs"
            params = {
                "limit": 500,
            }
            
            if current_since:
                params["since"] = current_since.isoformat().replace("+00:00", "Z")
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                raise Exception(f"Failed to fetch logs: {response.status_code} - {response.text}")
            
            data = response.json()
            logs_batch = data.get("logs", [])
            all_logs.extend(logs_batch)
            
            has_more = data.get("has_more", False)
            
            if has_more and logs_batch:
                last_log = logs_batch[-1]
                last_submitted = last_log.get("submitted_at")
                if last_submitted:
                    current_since = datetime.fromisoformat(last_submitted.replace("Z", "+00:00"))
            
            page += 1
            print(f"Fetched page {page}, got {len(logs_batch)} logs, total so far: {len(all_logs)}")
    
    return all_logs


async def load_items(items: list[dict], session: AsyncSession) -> int:
    from app.models.item import ItemRecord
    
    new_items_count = 0
    lab_map = {}
    
    for item in items:
        if item["type"] == "lab":
            statement = select(ItemRecord).where(
                ItemRecord.type == "lab",
                ItemRecord.title == item["title"]
            )
            result = await session.exec(statement)
            existing_lab = result.first()
            
            if not existing_lab:
                new_lab = ItemRecord(
                    type="lab",
                    title=item["title"]
                )
                session.add(new_lab)
                await session.flush()
                new_items_count += 1
                lab_map[item["lab"]] = new_lab
            else:
                lab_map[item["lab"]] = existing_lab
    
    for item in items:
        if item["type"] == "task":
            parent_lab = lab_map.get(item["lab"])
            if not parent_lab:
                print(f"Warning: No parent lab found for task {item['title']}")
                continue
            
            statement = select(ItemRecord).where(
                ItemRecord.type == "task",
                ItemRecord.title == item["title"],
                ItemRecord.parent_id == parent_lab.id
            )
            result = await session.exec(statement)
            existing_task = result.first()
            
            if not existing_task:
                new_task = ItemRecord(
                    type="task",
                    title=item["title"],
                    parent_id=parent_lab.id
                )
                session.add(new_task)
                new_items_count += 1
    
    await session.commit()
    
    return new_items_count


async def load_logs(
    logs: list[dict], items_catalog: list[dict], session: AsyncSession
) -> int:
    from app.models.learner import Learner
    from app.models.interaction import InteractionLog as InteractionLogModel
    from app.models.item import ItemRecord
    
    new_logs_count = 0
    
    title_map = {}
    for item in items_catalog:
        if item["type"] == "lab":
            title_map[(item["lab"], None)] = item["title"]
        else:
            title_map[(item["lab"], item["task"])] = item["title"]
    
    for log in logs:
        student_id = log["student_id"]
        statement = select(Learner).where(Learner.external_id == student_id)
        result = await session.exec(statement)
        learner = result.first()
        
        if not learner:
            learner = Learner(
                external_id=student_id,
                student_group=log.get("group", "unknown")
            )
            session.add(learner)
            await session.flush()
        
        item_key = (log["lab"], log["task"])
        item_title = title_map.get(item_key)
        
        if not item_title:
            print(f"Warning: No item found for {item_key}")
            continue
        
        statement = select(ItemRecord).where(ItemRecord.title == item_title)
        result = await session.exec(statement)
        item = result.first()
        
        if not item:
            print(f"Warning: Item with title '{item_title}' not found in DB")
            continue
        
        statement = select(InteractionLogModel).where(InteractionLogModel.external_id == log["id"])
        result = await session.exec(statement)
        existing_log = result.first()
        
        if existing_log:
            continue
        
        new_log = InteractionLogModel(
            external_id=log["id"],
            learner_id=learner.id,
            item_id=item.id,
            kind="attempt",
            score=log.get("score"),
            checks_passed=log["passed"],
            checks_total=log["total"],
            created_at=datetime.fromisoformat(log["submitted_at"].replace("Z", "+00:00"))
        )
        session.add(new_log)
        new_logs_count += 1
        
        if new_logs_count % 100 == 0:
            await session.commit()
    
    await session.commit()
    
    return new_logs_count


async def sync(session: AsyncSession) -> dict:
    items_data = await fetch_items()
    new_items = await load_items(items_data, session)
    print(f"Loaded {new_items} new items")
    
    from app.models.interaction import InteractionLog as InteractionLogModel
    
    statement = select(InteractionLogModel).order_by(InteractionLogModel.created_at.desc())
    result = await session.exec(statement)
    last_log = result.first()
    
    since = last_log.created_at if last_log else None
    if since:
        print(f"Fetching logs since: {since}")
    else:
        print("Fetching all logs (first run)")
    
    all_logs = await fetch_logs(since)
    print(f"Fetched {len(all_logs)} logs from API")
    
    if not all_logs:
        return {
            "new_records": 0,
            "total_records": 0
        }
    
    items_catalog = await fetch_items()
    new_logs = await load_logs(all_logs, items_catalog, session)
    print(f"Loaded {new_logs} new logs")
    
    statement = select(InteractionLogModel)
    result = await session.exec(statement)
    total_logs = result.all()
    total_count = len(total_logs)
    
    return {
        "new_records": new_logs,
        "total_records": total_count
    }